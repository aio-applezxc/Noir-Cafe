from noir import create_app

app = create_app()

if __name__ == "__main__":
    import os
    from waitress import serve
    serve(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")), threads=8)
