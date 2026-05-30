import sys

try:
    import strawberry
    version = getattr(strawberry, "__version__", "instalado")
    print(f"OK   strawberry-graphql: {version}")
except ImportError as e:
    print(f"ERRO strawberry-graphql: {e}")
    sys.exit(1)

try:
    from strawberry.fastapi import GraphQLRouter
    print("OK   strawberry FastAPI integration: funcionando")
except ImportError as e:
    print(f"ERRO strawberry FastAPI integration: {e}")
    sys.exit(1)

print("\nStrawberry GraphQL pronto!")
