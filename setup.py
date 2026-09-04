from setuptools import setup, find_packages

setup(
    name='audiomuxer-bot',
    version='1.0.0',
    description='AudioMuxer Pro Bot for Telegram',
    packages=find_packages(),
    install_requires=[
        'python-telegram-bot>=21.0',
        'httpx>=0.27.0',
        'python-dotenv>=1.0.0',
        'aiosqlite>=0.20.0',
        'pydantic>=2.5.0',
        'numpy>=1.26.0,<2.1.0',
        'scipy>=1.12.0',
        'librosa>=0.10.1',
        'soundfile>=0.12.1',
        'pyyaml>=6.0.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-asyncio>=0.23.0',
        ]
    },
    entry_points={
        'console_scripts': [
            'audiomuxer=bot.cli:main',
            'audiomuxer-bot=bot.main:main',
        ],
    },
    python_requires='>=3.10',
)
