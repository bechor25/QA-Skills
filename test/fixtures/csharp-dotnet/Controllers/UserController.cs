using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using MyApp.Models;
using MyApp.Services;

namespace MyApp.Controllers;

[ApiController]
[Route("api/[controller]")]
public class UsersController : ControllerBase
{
    private readonly IUserService _userService;

    public UsersController(IUserService userService) => _userService = userService;

    [HttpPost("/api/auth/login")]
    public async Task<IActionResult> Login([FromBody] LoginRequest req)
    {
        if (string.IsNullOrEmpty(req.Email) || string.IsNullOrEmpty(req.Password))
            return BadRequest(new { error = "Email and password required" });

        var token = await _userService.AuthenticateAsync(req.Email, req.Password);
        if (token == null) return Unauthorized(new { error = "Invalid credentials" });
        return Ok(new { token });
    }

    [HttpGet]
    [Authorize]
    public async Task<IActionResult> List([FromQuery] int page = 1, [FromQuery] int limit = 10)
    {
        var (items, total) = await _userService.GetAllAsync(page, limit);
        return Ok(new { items, total, page });
    }

    [HttpGet("{id}")]
    [Authorize]
    public async Task<IActionResult> GetById(string id)
    {
        var user = await _userService.GetByIdAsync(id);
        if (user == null) return NotFound(new { error = "User not found" });
        return Ok(new { user.Id, user.Email, user.Name, user.Role });
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateUserRequest req)
    {
        try
        {
            var user = await _userService.CreateAsync(req.Email, req.Password, req.Name);
            return StatusCode(201, new { user.Id, user.Email, user.Name, user.Role });
        }
        catch (InvalidOperationException ex)
        {
            return BadRequest(new { error = ex.Message });
        }
    }

    [HttpPut("{id}")]
    [Authorize]
    public async Task<IActionResult> Update(string id, [FromBody] UpdateUserRequest req)
    {
        var user = await _userService.UpdateAsync(id, req.Name);
        if (user == null) return NotFound(new { error = "User not found" });
        return Ok(new { user.Id, user.Email, user.Name, user.Role });
    }

    [HttpDelete("{id}")]
    [Authorize(Roles = "Admin")]
    public async Task<IActionResult> Delete(string id)
    {
        var deleted = await _userService.DeleteAsync(id);
        if (!deleted) return NotFound(new { error = "User not found" });
        return NoContent();
    }
}

public record LoginRequest(string Email, string Password);
public record CreateUserRequest(string Email, string Password, string Name);
public record UpdateUserRequest(string? Name);
