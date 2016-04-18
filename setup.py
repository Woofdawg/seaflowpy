from setuptools import setup

try:
    import pypandoc
    long_description = pypandoc.convert('README.md', 'rst')
except(IOError, ImportError):
    long_description = open('README.md').read()


setup(name='seaflowpy',
    use_scm_version=True,
    description='A Python library for SeaFlow data.',
    long_description=long_description,
    url='http://github.com/armbrustlab/seaflowpy',
    author='Chris T. Berthiaume',
    author_email='chrisbee@uw.edu',
    license='GPL3',
    packages=['seaflowpy'],
    install_requires=[
        'boto3',
        'numpy',
        'pandas',
        'setuptools_scm'
    ],
    setup_requires=['pytest-runner', 'setuptools_scm'],
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'seaflowpy_filter=seaflowpy.filterevt_cli:main',
            'seaflowpy_classify=seaflowpy.classifyopp_cli:main'
        ]
    },
    zip_safe=False
)
