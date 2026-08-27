"""Service signatures: how portlist decides what is actually running on a port.

Every signature carries a `sensitivity` used by the risk model:
    critical - direct data or execution access if reached (datastores, docker, model runners)
    high     - admin surfaces, notebooks, agent builders
    medium   - app servers that usually front something real
    low      - dev servers, static file serving

`ai=True` marks an AI/ML asset so it can be filtered and badged separately.
Matching is multi-signal; a port number alone is never enough to claim a service.
"""

# Weights per signal type. A claim needs >= 30 to be reported at all.
W_PROC = 45      # process name / command line - strongest local signal
W_BODY = 40      # unique string in the response body
W_TITLE = 35     # <title> match
W_HEADER = 35    # Server / X-Powered-By header
W_BANNER = 45    # raw protocol banner (SSH, MySQL, Redis, ...)
W_PATH = 40      # confirmed by a targeted endpoint
W_PORT = 15      # conventional port - a hint, never a conclusion

SERVICES = [
    # ---------------------------------------------------------------- AI / ML
    dict(id="ollama", name="Ollama", cat="AI model runner", ai=True,
         sensitivity="critical", ports=[11434], proc=[r"\bollama\b"],
         body=[r"Ollama is running"], header=[r"(?i)ollama"],
         path=("/api/tags", r'"models"'),
         note="Local LLM API. Unauthenticated by default: anyone who can reach it can run inference, pull models, and read model names."),
    dict(id="vllm", name="vLLM", cat="AI model server", ai=True,
         sensitivity="critical", ports=[8000], proc=[r"vllm", r"api_server"],
         title=[r"(?i)vllm"], path=("/v1/models", r'"object"\s*:\s*"list"'),
         note="OpenAI-compatible inference server, usually no auth."),
    dict(id="lmstudio", name="LM Studio", cat="AI model server", ai=True,
         sensitivity="critical", ports=[1234], proc=[r"(?i)lm.?studio"],
         path=("/v1/models", r'"object"')),
    dict(id="localai", name="LocalAI", cat="AI model server", ai=True,
         sensitivity="critical", ports=[8080], proc=[r"local-ai"],
         header=[r"(?i)localai"]),
    dict(id="openwebui", name="Open WebUI", cat="AI chat UI", ai=True,
         sensitivity="high", ports=[8080, 3000], proc=[r"open.?webui"],
         title=[r"(?i)open\s*webui"], body=[r"(?i)open-webui"],
         note="Chat front-end with saved conversations and API keys."),
    dict(id="jupyter", name="Jupyter", cat="Notebook server", ai=True,
         sensitivity="critical", ports=[8888, 8889], proc=[r"jupyter", r"ipykernel"],
         title=[r"(?i)jupyter"], header=[r"(?i)tornadoserver"],
         note="Notebooks execute arbitrary code as your user. Token auth can be disabled."),
    dict(id="mlflow", name="MLflow", cat="ML tracking", ai=True,
         sensitivity="high", ports=[5000], proc=[r"mlflow"], title=[r"(?i)mlflow"]),
    dict(id="comfyui", name="ComfyUI", cat="AI workflow UI", ai=True,
         sensitivity="high", ports=[8188], proc=[r"(?i)comfyui|comfy/main\.py"],
         title=[r"(?i)comfyui"]),
    dict(id="gradio", name="Gradio app", cat="AI app", ai=True,
         sensitivity="high", ports=[7860], proc=[r"gradio"],
         body=[r"gradio_config", r"(?i)gradio-app"]),
    dict(id="streamlit", name="Streamlit app", cat="AI app", ai=True,
         sensitivity="medium", ports=[8501], proc=[r"streamlit"],
         body=[r"(?i)streamlit"]),
    dict(id="langflow", name="Langflow", cat="Agent builder", ai=True,
         sensitivity="critical", ports=[7860, 3000], proc=[r"langflow"],
         title=[r"(?i)langflow"],
         note="Flow builder with stored provider credentials; flows can call out to anything."),
    dict(id="flowise", name="Flowise", cat="Agent builder", ai=True,
         sensitivity="critical", ports=[3000], proc=[r"flowise"],
         title=[r"(?i)flowise"]),
    dict(id="n8n", name="n8n", cat="Automation", ai=True,
         sensitivity="critical", ports=[5678], proc=[r"\bn8n\b"],
         title=[r"(?i)n8n"],
         note="Workflow engine holding credentials for every service it automates."),
    dict(id="dify", name="Dify", cat="Agent builder", ai=True,
         sensitivity="high", ports=[3000, 5001], proc=[r"dify"], title=[r"(?i)dify"]),
    dict(id="anythingllm", name="AnythingLLM", cat="AI chat UI", ai=True,
         sensitivity="high", ports=[3001], proc=[r"anythingllm"], title=[r"(?i)anythingllm"]),
    dict(id="qdrant", name="Qdrant", cat="Vector database", ai=True,
         sensitivity="critical", ports=[6333, 6334], proc=[r"qdrant"],
         body=[r'"title"\s*:\s*"qdrant'], note="Vector store: embeddings and payloads are readable."),
    dict(id="chroma", name="Chroma", cat="Vector database", ai=True,
         sensitivity="critical", ports=[8000], proc=[r"chroma"],
         path=("/api/v1/heartbeat", r"nanosecond heartbeat")),
    dict(id="weaviate", name="Weaviate", cat="Vector database", ai=True,
         sensitivity="critical", ports=[8080], proc=[r"weaviate"],
         path=("/v1/.well-known/ready", r"^$|ok")),
    dict(id="milvus", name="Milvus", cat="Vector database", ai=True,
         sensitivity="critical", ports=[19530, 9091], proc=[r"milvus"]),
    dict(id="mcp", name="MCP server", cat="Agent tooling", ai=True,
         sensitivity="critical",
         proc=[r"\bmcp[-_]server[\w-]*", r"modelcontextprotocol", r"@modelcontextprotocol",
               r"\bfastmcp\b", r"[-/]mcp\b(?!\.)"],
         body=[r"(?i)modelcontextprotocol", r'"jsonrpc"\s*:\s*"2\.0"'],
         note="A Model Context Protocol endpoint. Whoever can reach it can call every "
              "tool it exposes - filesystem, database, shell, cloud - with the server's "
              "own credentials, not theirs."),

    # ------------------------------------------------------------- datastores
    dict(id="redis", name="Redis", cat="Database", sensitivity="critical",
         ports=[6379], proc=[r"redis-server"], banner=[r"\+PONG", r"-NOAUTH", r"-ERR.*unauthenticated"],
         note="Key-value store. Without requirepass, reachable Redis means full data read/write."),
    dict(id="postgres", name="PostgreSQL", cat="Database", sensitivity="critical",
         ports=[5432], proc=[r"postgres", r"\bpg_ctl\b"]),
    dict(id="mysql", name="MySQL/MariaDB", cat="Database", sensitivity="critical",
         ports=[3306], proc=[r"mysqld", r"mariadbd"], banner=[r"mysql_native_password", r"MariaDB"]),
    dict(id="mongodb", name="MongoDB", cat="Database", sensitivity="critical",
         ports=[27017], proc=[r"mongod\b"]),
    dict(id="elasticsearch", name="Elasticsearch", cat="Search", sensitivity="critical",
         ports=[9200], proc=[r"elasticsearch"], body=[r'"cluster_name"']),
    dict(id="opensearch", name="OpenSearch", cat="Search", sensitivity="critical",
         ports=[9200], proc=[r"opensearch"], body=[r'"distribution"\s*:\s*"opensearch"']),
    dict(id="clickhouse", name="ClickHouse", cat="Database", sensitivity="critical",
         ports=[8123, 9000], proc=[r"clickhouse"], body=[r"^Ok\.\s*$"]),
    dict(id="memcached", name="memcached", cat="Cache", sensitivity="high",
         ports=[11211], proc=[r"memcached"]),
    dict(id="minio", name="MinIO", cat="Object storage", sensitivity="critical",
         ports=[9000, 9001], proc=[r"minio"], header=[r"(?i)minio"]),

    # ----------------------------------------------------------- infra / admin
    dict(id="docker", name="Docker API", cat="Container runtime", sensitivity="critical",
         ports=[2375, 2376], proc=[r"dockerd", r"com\.docker"], header=[r"(?i)docker"],
         note="The Docker API is root-equivalent. Exposed on a network interface it is game over."),
    dict(id="kubernetes", name="Kubernetes API", cat="Orchestrator", sensitivity="critical",
         ports=[6443, 8001], proc=[r"kube-apiserver", r"k3s"]),
    dict(id="portainer", name="Portainer", cat="Container UI", sensitivity="critical",
         ports=[9443, 9000], proc=[r"portainer"], title=[r"(?i)portainer"]),
    dict(id="grafana", name="Grafana", cat="Dashboards", sensitivity="high",
         ports=[3000], proc=[r"grafana"], title=[r"(?i)grafana"], header=[r"(?i)grafana"]),
    dict(id="prometheus", name="Prometheus", cat="Metrics", sensitivity="high",
         ports=[9090], proc=[r"prometheus"], title=[r"(?i)prometheus"]),
    dict(id="ssh", name="SSH", cat="Remote access", sensitivity="critical",
         ports=[22], banner=[r"^SSH-\d"]),
    dict(id="vnc", name="VNC / Screen Sharing", cat="Remote access", sensitivity="critical",
         ports=[5900, 5901], banner=[r"^RFB \d"]),
    dict(id="smb", name="SMB file sharing", cat="File sharing", sensitivity="high", ports=[445]),
    dict(id="tor", name="Tor", cat="Proxy", sensitivity="medium",
         ports=[9050, 9150, 9151], proc=[r"\btor\b"]),

    # ------------------------------------------------------------- web / dev
    dict(id="nginx", name="nginx", cat="Web server", sensitivity="medium",
         proc=[r"\bnginx\b"], header=[r"(?i)^nginx"]),
    dict(id="apache", name="Apache", cat="Web server", sensitivity="medium",
         proc=[r"httpd\b"], header=[r"(?i)^apache"]),
    dict(id="caddy", name="Caddy", cat="Web server", sensitivity="medium",
         proc=[r"\bcaddy\b"], header=[r"(?i)^caddy"]),
    dict(id="nextjs", name="Next.js", cat="App server", sensitivity="medium",
         ports=[3000], body=[r"__NEXT_DATA__", r"/_next/static"], header=[r"(?i)next\.js"]),
    dict(id="vite", name="Vite dev server", cat="Dev server", sensitivity="low",
         ports=[5173], body=[r"/@vite/client"]),
    dict(id="express", name="Node / Express", cat="App server", sensitivity="medium",
         header=[r"(?i)express"]),
    dict(id="uvicorn", name="FastAPI / Uvicorn", cat="App server", sensitivity="medium",
         proc=[r"uvicorn", r"fastapi"], header=[r"(?i)uvicorn"]),
    dict(id="gunicorn", name="Gunicorn", cat="App server", sensitivity="medium",
         proc=[r"gunicorn"], header=[r"(?i)gunicorn"]),
    dict(id="flask", name="Flask / Werkzeug", cat="App server", sensitivity="medium",
         header=[r"(?i)werkzeug"]),
    dict(id="django", name="Django", cat="App server", sensitivity="medium",
         proc=[r"manage\.py runserver"], header=[r"(?i)wsgiserver"]),
    dict(id="rails", name="Rails / Puma", cat="App server", sensitivity="medium",
         proc=[r"\bpuma\b", r"rails s"], header=[r"(?i)puma"]),
    dict(id="bun", name="Bun", cat="Dev server", sensitivity="low",
         proc=[r"\bbun\b"], header=[r"(?i)^bun$"]),
    dict(id="pyhttp", name="Python http.server", cat="Static file server", sensitivity="medium",
         proc=[r"http\.server", r"SimpleHTTPServer"], header=[r"(?i)simplehttp"],
         title=[r"^Directory listing for "],
         note="Serves its whole working directory with no auth, including dotfiles and keys if present."),
    dict(id="airplay", name="AirPlay Receiver", cat="macOS service", sensitivity="medium",
         ports=[5000, 7000], proc=[r"ControlCenter", r"AirPlay"],
         note="macOS AirPlay Receiver. Turn off in System Settings > General > AirDrop & Handoff."),
    dict(id="rapportd", name="Handoff / Continuity", cat="macOS service",
         sensitivity="low", proc=[r"rapportd"]),
    dict(id="vscode", name="VS Code helper", cat="Editor tooling", sensitivity="low",
         proc=[r"Code Helper", r"vscode-server", r"\.vscode/extensions"]),
    dict(id="chromedev", name="Browser dev endpoint", cat="Editor tooling", sensitivity="high",
         proc=[r"Google Chrome", r"Chromium"], ports=[9222],
         note="Chrome remote debugging gives full control of the browser profile."),
    dict(id="webpack", name="Webpack dev server", cat="Dev server", sensitivity="low",
         body=[r"webpack-dev-server", r"__webpack"]),
]

BY_ID = {s["id"]: s for s in SERVICES}

SENS_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}
