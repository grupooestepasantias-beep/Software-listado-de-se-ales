using System.Security.Cryptography;

namespace Play.Server.Services;

/// <summary>Hash PBKDF2 para PIN y contraseñas. Formato: iteraciones.salt.hash (base64).</summary>
public static class PinHasher
{
    private const int Iterations = 100_000;

    public static string NuevoPin() => RandomNumberGenerator.GetInt32(0, 10_000).ToString("D4");

    public static string NuevaClaveTemporal() =>
        Convert.ToBase64String(RandomNumberGenerator.GetBytes(9)).Replace('+', 'a').Replace('/', 'b');

    public static string Hash(string secret)
    {
        var salt = RandomNumberGenerator.GetBytes(16);
        var hash = Rfc2898DeriveBytes.Pbkdf2(secret, salt, Iterations, HashAlgorithmName.SHA256, 32);
        return $"{Iterations}.{Convert.ToBase64String(salt)}.{Convert.ToBase64String(hash)}";
    }

    public static bool Verify(string secret, string stored)
    {
        var parts = stored.Split('.');
        if (parts.Length != 3 || !int.TryParse(parts[0], out var iter)) return false;
        var salt = Convert.FromBase64String(parts[1]);
        var expected = Convert.FromBase64String(parts[2]);
        var actual = Rfc2898DeriveBytes.Pbkdf2(secret, salt, iter, HashAlgorithmName.SHA256, expected.Length);
        return CryptographicOperations.FixedTimeEquals(actual, expected);
    }
}
