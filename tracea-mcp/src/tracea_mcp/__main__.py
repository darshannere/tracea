"""Entry point: uvx tracea-mcp"""
from tracea_mcp.server import MCPServer


def main():
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
