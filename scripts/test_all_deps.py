import sys

libs_ok = True

checks = [
    ("pydantic",             "pydantic"),
    ("pydantic_settings",    "pydantic-settings"),
    ("langchain",            "langchain"),
    ("langchain_community",  "langchain-community"),
    ("langchain_core",       "langchain-core"),
    ("langgraph",            "langgraph"),
    ("langchain_ollama",     "langchain-ollama"),
    ("pymongo",              "pymongo"),
    ("motor",                "motor"),
    ("elasticsearch",        "elasticsearch"),
    ("confluent_kafka",      "confluent-kafka"),
    ("fastapi",              "fastapi"),
    ("uvicorn",              "uvicorn"),
    ("strawberry",           "strawberry-graphql"),
    ("loguru",               "loguru"),
    ("httpx",                "httpx"),
    ("aiohttp",              "aiohttp"),
    ("tenacity",             "tenacity"),
    ("bs4",                  "beautifulsoup4"),
    ("requests",             "requests"),
    ("opentelemetry",        "opentelemetry-api"),
    ("pytest",               "pytest"),
]

print()
print("=" * 50)
print("  DEPENDENCIAS INSTALADAS")
print("=" * 50)

for module, name in checks:
    try:
        mod = __import__(module)
        version = getattr(mod, "__version__", "OK")
        print(f"  OK   {name:<30} {version}")
    except ImportError:
        print(f"  ERRO {name:<30} NAO INSTALADO")
        libs_ok = False

print("=" * 50)

if libs_ok:
    print("\n  TUDO INSTALADO COM SUCESSO!")
else:
    print("\n  ALGUNS PACOTES FALTANDO - verifique acima.")

sys.exit(0 if libs_ok else 1)
