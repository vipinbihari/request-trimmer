from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="request_trimmer",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.0",
    ],
    entry_points={
        'console_scripts': [
            'request-trimmer=request_trimmer.cli:main',
        ],
    },
    author="Vipin",
    author_email="user@example.com",
    description="A tool to trim HTTP requests by removing unnecessary headers, cookies, and query parameters",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/request_trimmer",
    keywords="http, request, trim, optimize, headers, cookies, query parameters",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Testing",
        "Topic :: Utilities",
    ],
    python_requires=">=3.6",
)
