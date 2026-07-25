using System;
using System.Collections.Generic;

namespace Example
{
    /// <summary>A simple user with a name.</summary>
    public class SimpleClass
    {
        private string name;

        public SimpleClass(string name)
        {
            this.name = name;
        }

        /// <summary>Returns the stored value.</summary>
        public string GetValue()
        {
            return HelperMethod(name).Trim();
        }

        private static string HelperMethod(string input)
        {
            return input.ToUpper();
        }
    }

    public interface IRepository
    {
        List<SimpleClass> FindAll();
    }

    public struct Point
    {
        public int X;
        public int Y;
    }

    public enum Status
    {
#if LEGACY
        Deprecated,
#endif
        Active,
        Inactive
    }

    public record Person(string First, string Last);

    public record struct Coord(int X, int Y);

    public delegate void Handler(string message);
}
