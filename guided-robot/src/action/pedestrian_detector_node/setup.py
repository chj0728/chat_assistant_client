from setuptools import setup
import os
from glob import glob

package_name = 'pedestrian_detector_node'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/' + package_name + '/launch', ['launch/pedestrian_detector_node.launch.py']),
        ('share/' + package_name + '/config', ['config/pedestrian_detector_node.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='your_name',
    maintainer_email='your_email@example.com',
    description='Example ROS2 package with launch and config',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'pedestrian_detector_node = pedestrian_detector_node.pedestrian_detector_node:main',
        ],
    },
)