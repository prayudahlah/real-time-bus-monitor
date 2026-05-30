import time

def main():
    print("[CDC Consumer] Service ready — waiting for CDC events from batch")
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
