# Troubleshooting Documentation

## Table of Contents

1. [Troubleshooting Reference iDRAC MCP Server](#troubleshooting-reference-idrac-mcp-server)
2. [Troubleshooting Agentic Integration Test Workflows](#troubleshooting-agentic-integration-test-workflows)
3. [Troubleshooting Docker Deployment Failures](#troubleshooting-docker-deployment-failures)

## Troubleshooting Reference iDRAC MCP Server

### Tool Not Found

**Symptom**: "Tool not found in registry"

**Causes**:
- Tool not enabled in `tools.yaml`
- Invalid `operation_id` reference
- Workflow references non-existent tool

**Solution**:
- Check `enabled: true` in config
- Verify `operation_id` exists in OpenAPI spec
- Check server startup logs for validation errors

### Authentication Failures

**Symptom**: HTTP 401 errors

**Causes**:
- Incorrect credentials
- Expired token
- Missing credentials

**Solution**:
- Verify credentials
- Regenerate token if expired
- Ensure username+password OR auth_token provided

### Workflow Step Failures

**Symptom**: Workflow fails at specific step

**Causes**:
- Invalid parameter substitution
- JSONPath extraction failure
- Tool execution error

**Solution**:
- Check variable paths: `${{steps.name.output}}`
- Verify JSONPath against actual API response
- Test tool independently
- Review step `on_error` strategy

---

## Troubleshooting Agentic Integration Test Workflows

### Common Issues

**Issue**: "Orchestrator exited with code 1"
- **Cause**: Missing LLM API key
- **Fix**: Set `DEV_GENAI_API_KEY` in `.env`

**Issue**: "Tool execution failed: Authentication required"
- **Cause**: No credentials configured
- **Fix**: Add systems in Chat UI credential manager

**Issue**: "Multi-system execution not happening"
- **Cause**: Only one system configured
- **Fix**: Add multiple systems to see execution

**Issue**: "RAG search returns no results"
- **Cause**: Vector store not initialized
- **Fix**: Check `data/pdfs/` exists, restart orchestrator

---

## Troubleshooting Docker Deployment Failures

### Services Won't Start

**First, check if .env file exists**:
```bash
# This is the #1 cause of startup failures!
ls -la .env

# If missing, create it:
cp .env.example .env
# Edit with your credentials, then restart:
docker compose down && docker compose up -d
```

**Check logs**:
```bash
# Check logs for all services
docker compose logs

# Check specific service
docker compose logs orchestrator

# Look for authentication/credential errors
docker compose logs orchestrator | grep -i "api_key\|auth\|error"

# Check if ports are in use
sudo netstat -tulpn | grep -E '8000|8001|8501'
```

### Credential Database Issues

```bash
# Check if volume exists
docker volume ls | grep credentials

# Inspect volume
docker volume inspect idrac-credentials

# Reset database (WARNING: Deletes all credentials!)
docker compose down
docker volume rm idrac-credentials
docker compose up -d
```

### Connection Errors

```bash
# Test MCP server
curl http://localhost:8000/mcp

# Test orchestrator health
curl http://localhost:8001/health

# Test chat UI
curl http://localhost:8501/_stcore/health
```

### Memory Issues

```bash
# Check Docker resource limits
docker stats

# Increase Docker memory (Docker Desktop settings)
# Recommended: At least 4GB RAM for all services
```


