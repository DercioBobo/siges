from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="escola",
    version="0.1.0",
    description="Sistema de Gestão Escolar",
    author="EntreTech",
    author_email="info@entretech.co.mz",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
