#!/bin/bash

# 1. 解压缩 Ipopt_pkg.zip 到 /home/ymrobot 下
echo "解压缩 Ipopt_pkg.zip..."
unzip -q /home/ymrobot/Ipopt_pkg.zip -d /home/ymrobot
echo "解压缩完成。"

# 2. 安装必要的依赖
echo "安装依赖项..."
sudo apt-get update
sudo apt-get install -y gcc g++ gfortran git patch wget pkg-config liblapack-dev libmetis-dev libblas-dev
echo "依赖项安装完成。"

# 3. 进入 Ipopt_pkg 目录
cd /home/ymrobot/Ipopt_pkg

# 4. 编译 ThirdParty-ASL
echo "编译 ThirdParty-ASL..."
cd ThirdParty-ASL
sudo make
sudo make install
cd ..
echo "ThirdParty-ASL 编译完成。"

# 5. 编译 ThirdParty-HSL
echo "编译 ThirdParty-HSL..."
cd ThirdParty-HSL
sudo make
sudo make install
cd ..
echo "ThirdParty-HSL 编译完成。"

# 6. 安装 MUMPS 依赖并编译 ThirdParty-Mumps
echo "安装 MUMPS 依赖..."
sudo apt-get install -y libmumps-dev
echo "编译 ThirdParty-Mumps..."
cd ThirdParty-Mumps
sudo make
sudo make install
cd ..
echo "ThirdParty-Mumps 编译完成。"

# 7. 编译 Ipopt
echo "编译 Ipopt..."
cd Ipopt
mkdir -p build
cd build
sudo ../configure
sudo make
sudo make install
cd ../..
echo "Ipopt 编译完成。"

# 8. 配置库文件和符号链接
echo "配置库文件和符号链接..."
cd /usr/local/include
sudo cp -r coin-or coin
sudo ln -sf /usr/local/lib/libcoinmumps.so.3 /usr/lib/libcoinmumps.so.3
sudo ln -sf /usr/local/lib/libcoinhsl.so.2 /usr/lib/libcoinhsl.so.2
sudo ln -sf /usr/local/lib/libipopt.so.3 /usr/lib/libipopt.so.3
echo "库文件和符号链接配置完成。"

echo "所有步骤已完成！"
