from setuptools import find_packages, setup

package_name = "chat_assistant"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    package_data={package_name: ["web/web_server.html", "web/web_server.js"]},
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="xuyao",
    maintainer_email="997650637@qq.com",
    description="TODO: Package description",
    license="Apache-2.0",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": [
            "chat_assistant_node = chat_assistant.chat_assistant_node:main",
            "web_server = chat_assistant.web.web_server:main",
        ],
    },
)
