#include <queue>
#include <mutex>
#include <condition_variable>

// 线程安全队列模板类
template <typename T>
class ThreadSafeQueue {
public:
    // 向队列中添加元素
    void Push(const T &item) {
        std::lock_guard<std::mutex> lock(mutex_);
        queue_.push(item);
        condition_.notify_one(); // 通知等待线程
    }

    // 从队列中弹出元素（阻塞等待）
    bool Pop(T &item) {
        std::unique_lock<std::mutex> lock(mutex_);
        condition_.wait(lock, [this] { return !queue_.empty(); }); // 等待队列非空
        item = queue_.front();
        queue_.pop();
        return true;
    }

    // 尝试从队列中弹出元素（非阻塞）
    bool TryPop(T &item) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (queue_.empty()) {
            return false;
        }
        item = queue_.front();
        queue_.pop();
        return true;
    }

    // 获取队列大小
    size_t Size() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return queue_.size();
    }

private:
    mutable std::mutex mutex_;                   // 互斥锁，保护队列操作
    std::queue<T> queue_;                        // 标准队列
    std::condition_variable condition_;          // 条件变量，用于通知线程
};
