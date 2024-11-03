import uvicorn
import socket

def get_host_ip():
    try:
        # Create a dummy socket to a remote address
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # The address does not need to be reachable
            s.connect(("8.8.8.8", 80))  
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"  # Fallback to localhost

if __name__ == "__main__":
    host_ip = get_host_ip()
    port = 8001

    print("==========================================================")
    print("Your Fast API Host Is Changed To Below IP. Check Fast API Server By Visiting: http://[Below Ip]:8000/docs")
    print(host_ip)
    print("==========================================================")
    uvicorn.run("main:app", host=host_ip, port=port, reload=True)
