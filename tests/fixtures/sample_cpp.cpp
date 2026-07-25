#include <vector>
#include <string>
#include "local_header.hpp"

namespace example {

/// A simple user with a name.
class SimpleClass {
public:
    SimpleClass(std::string name);

    /// Returns the stored value.
    std::string getValue() const {
        return helperMethod(name_);
    }

    void declaredOnly() const;

private:
    static std::string helperMethod(const std::string& input);
    std::string name_;
};

SimpleClass::SimpleClass(std::string name) : name_(name) {}

std::string SimpleClass::helperMethod(const std::string& input) {
    return transform(input);
}

template <typename T>
T twice(T value) {
    return dup(value) + value;
}

struct Point {
    int x;
    int y;
};

enum class Color {
    Red,
    Green
};

using Handler = void (*)(int);

}  // namespace example
