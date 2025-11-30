#include "ymbot_hardware_driver/ymbot_hands_RTrobot_api.h"

RTrobot_hands::RTrobot_hands(const std::vector<int>& id,
                 const std::vector<int>& servo_max_positions,
                 const std::vector<int>& servo_min_positions) {
    if (id.size() != servo_max_positions.size() || id.size() != servo_min_positions.size()) {
        throw std::invalid_argument("The lengths of id, servo_max_positions, and servo_min_positions must be equal.");
    }

    id_ = id;
    servo_max_positions_ = servo_max_positions;
    servo_min_positions_ = servo_min_positions;

    std::cout << "RTrobot_hands object created successfully." << std::endl;
}

RTrobot_hands::~RTrobot_hands() {
    close(serial_port_);
    std::cout << "RTrobot_hands serial port closed." << std::endl;
}

bool RTrobot_hands::initialization(const char* port_name) {
    serial_port_ = open(port_name, O_RDWR | O_NOCTTY | O_NDELAY);
    if (serial_port_ == -1) {
        cerr << "Failed to open RTrobot_hands serial port : " << port_name << endl;
        return false;
    }

    struct termios RTrobot_hands_termios;
    bzero(&RTrobot_hands_termios, sizeof(RTrobot_hands_termios));
    RTrobot_hands_termios.c_cflag |= CLOCAL | CREAD;
    RTrobot_hands_termios.c_cflag &= ~CSIZE;
    cfsetispeed(&RTrobot_hands_termios, B115200);
    cfsetospeed(&RTrobot_hands_termios, B115200);
    RTrobot_hands_termios.c_cflag |= CS8;
    RTrobot_hands_termios.c_cflag &= ~PARENB;
    RTrobot_hands_termios.c_cflag &= ~CSTOPB;

    if ((tcsetattr(serial_port_, TCSANOW, &RTrobot_hands_termios)) != 0) {
        cerr << "Failed to set RTrobot_hands serial port parameters" << endl;
        close(serial_port_);
        return false;
    }
    return true;
}

void RTrobot_hands::set_position(const int id, const int target_position) {
    data_ += "#";
    data_ += to_string(id);
    data_ += "P";
    data_ += to_string(target_position);
}

void RTrobot_hands::set_velocity(const int target_velocity) {
    data_ += "T";
    data_ += to_string(target_velocity);
}

bool RTrobot_hands::send_data() {
    data_ += "\r\n";
    if (is_debug_) {
        cout << "RTrobot_hands instruction : " << data_ << endl;
    }
    int bytesWritten = write(serial_port_, data_.c_str(), data_.size());
    data_.resize(0);
    if (bytesWritten == -1) {
        cerr << "Failed to write to RTrobot_hands serial port." << endl;
        close(serial_port_);
        return false;
    }
    return true;
}

bool RTrobot_hands::receive_data() {
    constexpr int MaxBufferSize = 512;
    vector<uint8_t> buffer(MaxBufferSize);

    fd_set read_fds;
    FD_ZERO(&read_fds);
    FD_SET(serial_port_, &read_fds);

    struct timeval timeout;
    timeout.tv_sec = 0;
    timeout.tv_usec = 200000000;

    int result = select(serial_port_ + 1, &read_fds, nullptr, nullptr, &timeout);

    if (result == -1) {
        cerr << "Error using select() on the serial port" << endl;
        return false;
    }
    else if (result == 0) {
        cerr << "Receive failed: No data available within 2000ms" << endl;
        return false;
    }

    ssize_t bytesRead = read(serial_port_, buffer.data(), MaxBufferSize);

    if (bytesRead <= 0) {
        cerr << "Error reading from RTrobot_hands serial port or no data available" << endl;
        return false;
    }

    return true;
}

bool RTrobot_hands::stop_action() {
    data_.resize(0);
    data_ += "#STOP\r\n";
    if (is_debug_) {
        cout << "RTrobot_hands instruction : " << data_ << endl;
    }
    int bytesWritten = write(serial_port_, data_.c_str(), data_.size());
    if (bytesWritten == -1) {
        cerr << "Failed to write to RTrobot_hands serial port." << endl;
        close(serial_port_);
        return false;
    }
    data_.resize(0);
    return true;
}

bool RTrobot_hands::reset() {
    data_.resize(0);
    data_ += "~RE";
    if (is_debug_) {
        cout << "RTrobot_hands instruction : " << data_ << endl;
    }
    int bytesWritten = write(serial_port_, data_.c_str(), data_.size());
    if (bytesWritten == -1) {
        cerr << "Failed to write to RTrobot_hands serial port." << endl;
        close(serial_port_);
        return false;
    }
    data_.resize(0);
    return true;
}

bool RTrobot_hands::run_action_group(int action_group_num) {
    data_.resize(0);
    data_ += "#";
    data_ += to_string(action_group_num);
    data_ += "G";
    data_ += "C1";
    data_ += "\r\n";
    if (is_debug_) {
        cout << "RTrobot_hands instruction : " << data_ << endl;
    }
    int bytesWritten = write(serial_port_, data_.c_str(), data_.size());
    if (bytesWritten == -1) {
        cerr << "Failed to write to RTrobot_hands serial port." << endl;
        close(serial_port_);
        return false;
    }
    // cout << data_ << endl;
    data_.resize(0);
    return receive_data();
}

bool RTrobot_hands::control_servos(const vector<int> target_position, const int target_velocity) {
    if (id_.size() != target_position.size()) {
        std::cerr << "Error: The number of servo IDs and target positions do not match." << std::endl;
        return false;
    }

    for (size_t i = 0; i < id_.size(); ++i) {
        int id = id_[i];
        int pos = target_position[i];
        int max_pos = servo_max_positions_[i];
        int min_pos = servo_min_positions_[i];

        if (pos < min_pos || pos > max_pos) {
            std::cerr << "Error: Target position for servo ID " << id << " is out of range. Target position: " << pos
                      << ", Min: " << min_pos << ", Max: " << max_pos << std::endl;
            return false;
        }
    }

    for (int i = 0; i < id_.size(); i++) {
        set_position(id_[i], target_position[i]);
    }
    set_velocity(target_velocity);
    send_data();
    return receive_data();
}
