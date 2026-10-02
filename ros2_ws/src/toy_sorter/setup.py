from setuptools import find_packages, setup

package_name = "toy_sorter"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["tests"]),
    install_requires=["setuptools"],
    entry_points={
        "console_scripts": [
            "toy_sorter_sim = toysorter.tools.sim_cli:main",
        ],
    },
)
