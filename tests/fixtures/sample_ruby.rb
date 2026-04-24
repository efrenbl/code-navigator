# Sample Ruby file for testing the code mapper.

# Module declaration
module Validators
  # Class with inheritance
  class EmailValidator < BaseValidator
    # Class method
    def self.valid_format?(email)
      email.match?(/\A[\w+\-.]+@[a-z\d\-]+\.[a-z]+\z/i)
    end

    # Instance method
    def validate(record)
      unless self.class.valid_format?(record.email)
        record.errors.add(:email, "is invalid")
      end
    end
  end
end

# Top-level function
def greet(name)
  "Hello, #{name}!"
end

# Simple class
class SimpleClass
  def initialize(value)
    @value = value
  end

  def get_value
    @value
  end

  def set_value!(new_value)
    @value = new_value
  end

  def value_present?
    !@value.nil?
  end
end

# Derived class
class DerivedClass < SimpleClass
  def initialize(value, name)
    super(value)
    @name = name
  end

  def get_name
    @name
  end
end
