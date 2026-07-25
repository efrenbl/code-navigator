<?php

namespace Example;

use Example\Models\User;
use Example\Contracts\Formatter;

require_once 'lib/helpers.php';

/**
 * Greets someone by name.
 */
function greet(string $name): string
{
    return format_name($name);
}

/** A simple user service. */
class SimpleClass
{
    private string $name;

    public function __construct(string $name)
    {
        $this->name = $name;
    }

    /** Returns the stored value. */
    public function getValue(): string
    {
        return $this->formatter->format(greet($this->name));
    }
}

interface Repository
{
    public function findAll(): array;
}

trait Loggable
{
    public function log(string $message): void
    {
    }
}

enum Status: string
{
    case Active = 'active';
    case Inactive = 'inactive';
}
