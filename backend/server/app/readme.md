/api/sse/{task_id}	GET	SSE 流式推送任务状态更新
/api/reload-config	POST	重新加载 agent 配置
/api/start-task	POST	启动新任务并分发给多个 agent
/api/callback/{task_id}/{agent_type}	POST	Agent 回调接口
/api/tasks/{user_id}	GET	获取某个用户的所有任务
/api/health	GET	健康检查