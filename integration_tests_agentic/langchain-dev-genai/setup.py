from setuptools import setup, find_packages

setup(
    name="langchain-dev-genai",
    version="0.1.0",
    author="Cyril Jose",
    author_email="cyril.jose@dell.com",
    description="Langchain partner package to connect to dell dev-gen AI llm instances",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/update",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=[
        "langchain-core<1.0.0,>=0.3.66",
        "httpx<1.0.0,>=0.27.0",
        "pydantic<3.0.0,>=2.0.0",
    ],
)
