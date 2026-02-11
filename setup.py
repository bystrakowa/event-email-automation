from setuptools import setup, find_packages

setup(
    name="event_emailer",
    version="0.1.1",
    packages=find_packages(),
    install_requires=[
        "flexus-client-kit",
        "google-auth",
        "google-auth-oauthlib",
        "google-auth-httplib2",
        "google-api-python-client",
        "motor",
        "pymongo",
        "pytest-asyncio",
    ],
    package_data={"": ["*.webp", "*.png", "*.html", "*.lark", "*.json"]},
)
