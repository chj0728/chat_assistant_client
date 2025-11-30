from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'aud_conver'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name, f'{package_name}.client_modules'],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='fish',
    maintainer_email='2209655337@qq.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'audio_player_node = aud_conver.aud_fix:main',
            'audio_client_node = aud_conver.aud_fix_client:main',
            'audio_server = aud_conver.conver_server:main',
            'audio_auto = aud_conver.aud_conver_v:main',
            'image_converter=aud_conver.img_test:main',
        ],
    },
    package_data={
        package_name: [
            'client_modules/*.py',
            'client_modules/*/*.py',
            'client_modules/*/*/*.py',
            'client_modules/*/bin/resource/*',
        ],
    },
)