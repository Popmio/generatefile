import httpx
import asyncio

async def listen_sse(user_id:str,task_id: str,token: str):
    url = f"http://localhost:8000/api/sse/{user_id}/{task_id}?token={token}"

    async with httpx.AsyncClient(timeout=600) as client:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                print(f"Error: {response.status_code}")
                return

            async for line in response.aiter_lines():
                if line:
                    print("Received event:", line)

# 运行测试
asyncio.run(listen_sse("test_user", "f94d8464-3c3d-48fd-a812-1b1431c51465", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0YXNrX2lkIjoiZjk0ZDg0NjQtM2MzZC00OGZkLWE4MTItMWIxNDMxYzUxNDY1IiwidXNlcl9pZCI6InRlc3RfdXNlciIsImV4cCI6MTc1MzA4NTUyNH0._gpJUJkMzZPK4AlFeVrzKnuNypIFkV-lQPVR7dhnXdU"))