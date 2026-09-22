from setuptools import setup

setup(
    name="perfect",
    version="0.0.2",
    description="PERFormance Evaluation Composable Toolsuite",
    author="Daniel Robert Hunter",
    author_email="drhunter@umd.edu",
    url="https://code.umd.edu/drhunter/perfect",
    python_requires=">=3.8, <4",
    install_requires=[
        "flask>=2.2.2",
        "flask-migrate>=4.0.5",
        "flask-sqlalchemy>=3.0.2",
        "flask-wtf>=1",
        "jsonschema>=4.22",
        "jinja2>=3.1.2",
        "pyyaml>=6.0.2",
        "redis>=5.0.6",
        "rq>=1.15.1",
        "sqlalchemy-serializer>=1.4",
        "websockets>=12.0",
    ],
)
