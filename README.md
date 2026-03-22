# Forecast

Repository structure is now split by application surface:

- `frontend/`: Next.js dashboard application
- `backend/langchain/`: main Python backend with LangChain, FastAPI, Alembic, tests, and data assets
- `backend/mcp/`: MCP server code and docs
- `backend/tools/`: supporting backend utilities such as the Gmail sender and scraping scripts

## Common Working Directories

- Frontend work: `frontend`
- LangChain backend work: `backend/langchain`
- MCP work: `backend/mcp`
- Gmail tool work: `backend/tools/gmail_email_tool`
