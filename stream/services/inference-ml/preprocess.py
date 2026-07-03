import logging
from datetime import datetime
from collections import defaultdict
import psycopg2
from geopy.distance import distance

logger = logging.getLogger(__name__)

stops_cache = []
trips_cache = {}
batch_db_config = None

def set_batch_config(config):
    global batch_db_config
    batch_db_config = config

def load_gtfs_data(db_config):
    global stops_cache, trips_cache
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT stop_id, stop_lat, stop_lon FROM stops")
        stops_cache = [(r[0], r[1], r[2]) for r in cur.fetchall()]
        cur.execute("""
            SELECT t.trip_id, t.route_id, st.stop_sequence, st.stop_id, s.stop_lat, s.stop_lon
            FROM trips t
            JOIN stop_times st ON t.trip_id = st.trip_id
            JOIN stops s ON st.stop_id = s.stop_id
            ORDER BY t.trip_id, st.stop_sequence
        """)
        trips_data = defaultdict(list)
        for row in cur.fetchall():
            trip_id, route_id, seq, stop_id, lat, lon = row
            trips_data[trip_id].append({
                'route_id': route_id,
                'stop_sequence': seq,
                'stop_id': stop_id,
                'stop_lat': lat,
                'stop_lon': lon,
            })
        trips_cache = dict(trips_data)
        conn.close()
        stop_count = len(stops_cache)
        trip_count = len(trips_cache)
        logger.info(f"Loaded {stop_count} stops, {trip_count} trips from stream PG")
        return stop_count
    except Exception as e:
        logger.error(f"Failed to load GTFS data: {e}")
        return 0


def ensure_trip_loaded(trip_id):
    global trips_cache, batch_db_config
    if trip_id in trips_cache:
        return True
    if not batch_db_config:
        logger.warning(f"Trip {trip_id} not in cache and no batch DB configured")
        return False
    try:
        conn = psycopg2.connect(**batch_db_config)
        cur = conn.cursor()
        cur.execute("""
            SELECT st.stop_sequence, st.stop_id, s.stop_lat, s.stop_lon
            FROM stop_times st
            JOIN stops s ON st.stop_id = s.stop_id
            WHERE st.trip_id = %s
            ORDER BY st.stop_sequence
        """, (trip_id,))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return False
        trips_cache[trip_id] = [
            {'stop_sequence': r[0], 'stop_id': r[1], 'stop_lat': r[2], 'stop_lon': r[3]}
            for r in rows
        ]
        logger.info(f"Lazy-loaded trip {trip_id} ({len(rows)} stops)")
        return True
    except Exception as e:
        logger.error(f"Failed to lazy-load trip {trip_id}: {e}")
        return False

def find_nearest_stop(lat, lon):
    best_id = None
    best_dist = float('inf')
    best_lat = None
    best_lon = None
    for sid, slat, slon in stops_cache:
        d = distance((lat, lon), (slat, slon)).meters
        if d < best_dist:
            best_dist = d
            best_id = sid
            best_lat = slat
            best_lon = slon
    return best_id, best_lat, best_lon, best_dist

def compute_features(lat, lon, trip_id, timestamp):
    current_id, current_lat, current_lon, dist_to_stop = find_nearest_stop(lat, lon)
    trip_data = trips_cache.get(trip_id, [])
    if not trip_data:
        if ensure_trip_loaded(trip_id):
            trip_data = trips_cache.get(trip_id, [])
        else:
            for tid, stops in trips_cache.items():
                for s in stops:
                    if s['stop_id'] == current_id:
                        trip_data = stops
                        trip_id = tid
                        break
                if trip_data:
                    break
    if not trip_data:
        logger.warning(f"No trip data for stop {current_id}")
        return None
    current_seq = None
    for s in trip_data:
        if s['stop_id'] == current_id:
            current_seq = s['stop_sequence']
            break
    if current_seq is None:
        best_match = None
        best_dist = float('inf')
        for s in trip_data:
            d = distance((lat, lon), (s['stop_lat'], s['stop_lon'])).meters
            if d < best_dist:
                best_dist = d
                best_match = s
        if best_match:
            current_seq = best_match['stop_sequence']
            current_id = best_match['stop_id']
            current_lat = best_match['stop_lat']
            current_lon = best_match['stop_lon']
        else:
            logger.warning(f"No matching stop near trip {trip_id}")
            return None
    next_stop = None
    for s in trip_data:
        if s['stop_sequence'] == current_seq + 1:
            next_stop = s
            break
    if next_stop is None:
        logger.warning(f"Bus at last stop (seq {current_seq}) of trip {trip_id}")
        return None
    distance_to_next_m = distance(
        (current_lat, current_lon), (next_stop['stop_lat'], next_stop['stop_lon'])
    ).meters
    stop_sequence = current_seq
    hour_of_day = datetime.fromtimestamp(timestamp).hour
    total_stops = len(trip_data)
    stop_position_pct = stop_sequence / total_stops if total_stops > 0 else 0
    features = {
        'distance_to_next_m': round(distance_to_next_m, 2),
        'stop_sequence': stop_sequence,
        'hour_of_day': hour_of_day,
        'stop_position_pct': round(stop_position_pct, 4),
    }
    meta = {
        'current_stop_id': current_id,
        'next_stop_id': next_stop['stop_id'],
        'distance_to_stop_m': round(dist_to_stop, 2),
        'total_stops': total_stops,
    }
    return features, meta
