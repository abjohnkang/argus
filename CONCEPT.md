Argus - On-Device AI agent

We're going to build an On-Device AI agent based on Llama 4. We will run all associated modules through Docker.

We will have a following two scripts:
- run_debug.sh: run Docker in debug mode which can see all debug logs
- run_server.sh: run Docker

For the Docker application, we will use docker-compose.yml to install all the necessary modules in the Docker container, so that there are no impacts for the current computing environment.

when user runs run_debug.sh or run_server.sh, install necessary modules automatically if it doesn't exist.

As an initial step, let's impliment web-based chat bot like chatGPT.