#!/bin/bash
export PYTHONPATH=.
./backend/venv/bin/python -m backend.main > server_out.log 2>&1 &
SERVER_PID=$!
sleep 3
# 1. Start a new chat session to get a valid session_id (which sets up an empty Conversation record)
# Wait, /api/chat/new requires auth. But I can't generate a token easily in bash.
