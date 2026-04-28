using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using MyApp.Models;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;

namespace MyApp.Services;

public interface IUserService
{
    Task<string?> AuthenticateAsync(string email, string password);
    Task<User?> GetByIdAsync(string id);
    Task<(IEnumerable<User> Items, int Total)> GetAllAsync(int page, int limit);
    Task<User> CreateAsync(string email, string password, string name);
    Task<User?> UpdateAsync(string id, string? name);
    Task<bool> DeleteAsync(string id);
}

public class UserService : IUserService
{
    private readonly AppDbContext _context;
    private readonly IConfiguration _config;

    public UserService(AppDbContext context, IConfiguration config)
    {
        _context = context ?? throw new ArgumentNullException(nameof(context));
        _config = config;
    }

    public async Task<string?> AuthenticateAsync(string email, string password)
    {
        if (string.IsNullOrEmpty(email) || string.IsNullOrEmpty(password))
            throw new ArgumentException("Email and password required");

        var user = await _context.Users.FirstOrDefaultAsync(u => u.Email == email);
        if (user == null || !BCrypt.Net.BCrypt.Verify(password, user.PasswordHash))
            return null;

        return GenerateToken(user);
    }

    public async Task<User?> GetByIdAsync(string id) =>
        await _context.Users.FindAsync(id);

    public async Task<(IEnumerable<User> Items, int Total)> GetAllAsync(int page, int limit)
    {
        var query = _context.Users.OrderBy(u => u.CreatedAt);
        var total = await query.CountAsync();
        var items = await query.Skip((page - 1) * limit).Take(limit).ToListAsync();
        return (items, total);
    }

    public async Task<User> CreateAsync(string email, string password, string name)
    {
        if (await _context.Users.AnyAsync(u => u.Email == email))
            throw new InvalidOperationException("Email already registered");

        var user = new User
        {
            Email = email,
            Name = name,
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(password),
        };
        _context.Users.Add(user);
        await _context.SaveChangesAsync();
        return user;
    }

    public async Task<User?> UpdateAsync(string id, string? name)
    {
        var user = await _context.Users.FindAsync(id);
        if (user == null) return null;
        if (name != null) user.Name = name;
        await _context.SaveChangesAsync();
        return user;
    }

    public async Task<bool> DeleteAsync(string id)
    {
        var user = await _context.Users.FindAsync(id);
        if (user == null) return false;
        _context.Users.Remove(user);
        await _context.SaveChangesAsync();
        return true;
    }

    private string GenerateToken(User user)
    {
        var secret = _config["Jwt:Secret"] ?? "change-me-in-production-at-least-32-chars";
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret));
        var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);
        var claims = new[]
        {
            new Claim(JwtRegisteredClaimNames.Sub, user.Id),
            new Claim(ClaimTypes.Role, user.Role.ToString()),
        };
        var token = new JwtSecurityToken(
            claims: claims,
            expires: DateTime.UtcNow.AddHours(1),
            signingCredentials: creds);
        return new JwtSecurityTokenHandler().WriteToken(token);
    }
}
