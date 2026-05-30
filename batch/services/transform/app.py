import time

def main():
    print("[Transform] Service ready — waiting for Airflow DAG trigger")
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
