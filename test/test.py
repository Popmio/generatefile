from fastapi import FastAPI
import asyncio

app = FastAPI()

async def background_task(task_id: int):
    print(f"Task {task_id} started")
    await asyncio.sleep(10)
    print(f"Task {task_id} completed")

@app.post("/run-task")
async def run_task():
    task_id = 123

    response = {"status": "accepted", "task_id": task_id}

    asyncio.create_task(background_task(task_id))

    return response