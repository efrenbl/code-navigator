import Foundation
import UIKit

/// Greets someone by name.
func greet(name: String) -> String {
    return formatName(name)
}

class SimpleClass {
    var name: String = ""

    init(name: String) {
        self.name = name
    }

    /// Returns the stored value.
    func getValue() -> String {
        return greet(name: name)
    }
}

final class Subclass: SimpleClass {
    func extra() {}
}

struct Point {
    var x: Int
    var y: Int
}

protocol Repository {
    func findAll() -> [SimpleClass]
}

enum Status {
    case active
    case inactive
}

extension SimpleClass {
    func farewell() -> String {
        return "bye"
    }
}

typealias Handler = (String) -> Void
