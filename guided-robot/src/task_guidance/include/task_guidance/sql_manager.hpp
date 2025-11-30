#ifndef SQL_MANAGER_HPP
#define SQL_MANAGER_HPP

#include <iostream>
#include <string>
#include <map>
#include <variant>
#include <vector>
#include <fstream>
#include <sstream>
#include <type_traits>

class SqlManagernNode
{
public:
    // void initDatabase(SQLite::Database &db, const std::string &tableName);                                                                                // 初始化数据库及表格
    // void insertData(SQLite::Database &db, const std::string &tableName, const std::map<std::string, std::variant<std::string, int, double>> &columns);    // 插入数据，支持不同数据类型
    // std::map<std::string, std::variant<std::string, int, double>> getRowData(SQLite::Database &db, const std::string &tableName, int rowId);              // 获取某行数据
    // std::vector<std::variant<std::string, int, double>> getColumnData(SQLite::Database &db, const std::string &tableName, const std::string &columnName); // 获取某列数据

    // 获取csv文件某列所有数据 从0开始 
    std::vector<std::string> GetColumnFromCSV(const std::string& filePath, int columnIndex) {
        std::vector<std::string> columnData;
        std::ifstream file(filePath);
    
        if (!file.is_open()) {
            std::cerr << "Error: Could not open file " << filePath << std::endl;
            return columnData;
        }
    
        std::string line;
        while (std::getline(file, line)) {
            std::stringstream ss(line);
            std::string cell;
            int currentColumn = 0;
    
            while (std::getline(ss, cell, ',')) {
                if (currentColumn == columnIndex) {
                    columnData.push_back(cell);
                    break;
                }
                currentColumn++;
            }
        }
    
        file.close();
        return columnData;
    }

    /**
     * 写入CSV文件（支持动态表头+多格式数据）
     * @param filename  文件路径
     * @param headers   表头数组（可包含不同类型）
     * @param data      数据行二维数组
     * @param append    是否追加模式
     */
    template <typename... Headers>
    void WriteCSVWithHeaders(
        const std::string &filename,
        const std::vector<std::string> &headers,
        const std::vector<std::vector<std::string>> &data,
        bool append = false)
    {
        // 检查文件是否存在
        bool fileExists = std::filesystem::exists(filename);

        // 设置文件打开模式‌:ml-citation{ref="4,6" data="citationList"}
        std::ios_base::openmode mode = std::ios::out;
        if (append && fileExists)
        {
            mode |= std::ios::app;
        }
        else
        {
            mode |= std::ios::trunc;
        }

        // 打开文件并设置UTF-8编码‌:ml-citation{ref="5" data="citationList"}
        std::ofstream file(filename, mode);
        file.imbue(std::locale(file.getloc(), new std::codecvt_utf8<wchar_t>));

        // 写入表头（仅在文件新建或非追加模式时写入）‌:ml-citation{ref="5,6" data="citationList"}
        if (!fileExists || !append)
        {
            for (size_t i = 0; i < headers.size(); ++i)
            {
                file << headers[i];
                if (i != headers.size() - 1)
                    file << ",";
            }
            file << "\n";
        }

        // 写入数据行‌:ml-citation{ref="1,3" data="citationList"}
        for (const auto &row : data)
        {
            for (size_t i = 0; i < row.size(); ++i)
            {
                file << row[i];
                if (i != row.size() - 1)
                    file << ",";
            }
            file << "\n";
        }
        file.close();
    }

    /**
     * 查找CSV文件中指定列的匹配行
     * @param filename  文件路径
     * @param targetCol 目标列索引（从0开始）
     * @param searchVal 要查找的值
     * @return 包含所有匹配行的二维数组
     */
    std::vector<std::vector<std::string>> FindRowsByColumn(
        const std::string &filename,
        int targetCol,
        const std::string &searchVal)
    {
        std::vector<std::vector<std::string>> result;
        std::ifstream file(filename);

        if (!file.is_open())
        {
            std::cerr << "Error opening file: " << filename << std::endl;
            return result;
        }

        std::string line;
        while (std::getline(file, line))
        {
            std::vector<std::string> row;
            std::stringstream ss(line);
            std::string cell;

            // 分割行数据‌:ml-citation{ref="3" data="citationList"}
            while (std::getline(ss, cell, ','))
            {
                row.push_back(cell);
            }

            // 检查列索引有效性‌:ml-citation{ref="4" data="citationList"}
            if (targetCol < row.size() && row[targetCol] == searchVal)
            {
                result.push_back(row);
            }
        }

        file.close();
        return result;
    }

    /**
     * 通过列名查找数据行
     * @param filename  文件路径
     * @param colName   目标列名称
     * @param searchVal 要查找的值
     * @return 包含所有匹配行的二维数组
     */
    std::vector<std::vector<std::string>> FindRowsByColumnName(
        const std::string &filename,
        const std::string &colName,
        const std::string &searchVal)
    {
        std::ifstream file(filename);
        std::vector<std::vector<std::string>> result;

        if (!file.is_open())
        {
            std::cerr << "Error opening file: " << filename << std::endl;
            return result;
        }

        // 读取表头确定列索引‌:ml-citation{ref="6" data="citationList"}
        std::string headerLine;
        std::getline(file, headerLine);

        std::vector<std::string> headers;
        std::stringstream ssHeader(headerLine);
        std::string headerCell;

        int targetCol = -1;
        while (std::getline(ssHeader, headerCell, ','))
        {
            headers.push_back(headerCell);
            if (headerCell == colName)
            {
                targetCol = headers.size() - 1;
            }
        }

        if (targetCol == -1)
        {
            std::cerr << "Column not found: " << colName << std::endl;
            return result;
        }

        // 继续处理数据行‌:ml-citation{ref="3" data="citationList"}
        std::string dataLine;
        while (std::getline(file, dataLine))
        {
            std::vector<std::string> row;
            std::stringstream ss(dataLine);
            std::string cell;

            while (std::getline(ss, cell, ','))
            {
                row.push_back(cell);
            }

            if (targetCol < row.size() && row[targetCol] == searchVal)
            {
                result.push_back(row);
            }
        }

        file.close();
        return result;
    }
};
#endif // SQL_MANAGER_HPP