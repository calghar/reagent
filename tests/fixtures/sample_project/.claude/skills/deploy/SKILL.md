---
name: deploy
description: Deploy to staging and production
user-invocable: true
---

# /deploy -- Deploy Application

## Steps

1. Run the test suite: `pytest`
2. Build the Docker image: `docker build -t app .`
3. Push to registry
4. WAIT for human approval before proceeding
5. Deploy to staging environment
