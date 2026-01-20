/**
 * Sample TypeScript file for testing code navigation.
 * Contains interfaces, types, enums, generics, and TypeScript-specific features.
 */

// Simple interface
interface User {
    id: number;
    name: string;
    email: string;
}

// Interface with optional properties and methods
interface Config {
    host: string;
    port: number;
    debug?: boolean;
    onConnect?(): void;
}

// Interface with generics
interface Repository<T> {
    find(id: number): T | null;
    findAll(): T[];
    save(entity: T): T;
    delete(id: number): boolean;
}

// Interface extending another
interface AdminUser extends User {
    role: 'admin';
    permissions: string[];
}

// Type alias - union
type Status = 'pending' | 'active' | 'inactive' | 'deleted';

// Type alias - intersection
type UserWithStatus = User & { status: Status };

// Type alias with generics
type Result<T, E = Error> = { success: true; data: T } | { success: false; error: E };

// Type alias - mapped type
type Readonly<T> = {
    readonly [K in keyof T]: T[K];
};

// Regular enum
enum Color {
    Red,
    Green,
    Blue,
}

// String enum
enum Direction {
    Up = 'UP',
    Down = 'DOWN',
    Left = 'LEFT',
    Right = 'RIGHT',
}

// Const enum
const enum HttpStatus {
    OK = 200,
    NotFound = 404,
    InternalError = 500,
}

// Function with type annotations
function processUser(user: User): string {
    return `Processing ${user.name} (${user.email})`;
}

// Async function with generics
async function fetchEntity<T>(url: string): Promise<T> {
    const response = await fetch(url);
    return response.json() as T;
}

// Arrow function with types
const formatUser = (user: User): string => {
    return `${user.name} <${user.email}>`;
};

// Generic arrow function
const createArray = <T>(length: number, value: T): T[] => {
    return Array(length).fill(value);
};

// Class with implements
class UserRepository implements Repository<User> {
    private users: Map<number, User> = new Map();

    find(id: number): User | null {
        return this.users.get(id) || null;
    }

    findAll(): User[] {
        return Array.from(this.users.values());
    }

    save(entity: User): User {
        this.users.set(entity.id, entity);
        return entity;
    }

    delete(id: number): boolean {
        return this.users.delete(id);
    }
}

// Generic class
class Stack<T> {
    private items: T[] = [];

    push(item: T): void {
        this.items.push(item);
    }

    pop(): T | undefined {
        return this.items.pop();
    }

    peek(): T | undefined {
        return this.items[this.items.length - 1];
    }

    get size(): number {
        return this.items.length;
    }
}

// Abstract class
abstract class BaseService {
    protected abstract endpoint: string;

    async get<T>(id: number): Promise<T> {
        return fetchEntity<T>(`${this.endpoint}/${id}`);
    }

    abstract validate(data: unknown): boolean;
}

// Class extending abstract class
class UserService extends BaseService {
    protected endpoint = '/api/users';

    validate(data: unknown): boolean {
        return typeof data === 'object' && data !== null && 'name' in data;
    }

    async findByEmail(email: string): Promise<User | null> {
        const users = await fetchEntity<User[]>(this.endpoint);
        return users.find(u => u.email === email) || null;
    }
}

// Exported types
export type { User, Config, Repository };
export { Color, Direction, UserRepository, UserService };
