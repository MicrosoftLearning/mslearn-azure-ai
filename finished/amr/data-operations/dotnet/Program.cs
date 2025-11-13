//usr/bin/env dotnet-script
#r "nuget: StackExchange.Redis, 2.8.16"
#r "nuget: dotenv.net, 3.2.1"

using StackExchange.Redis;
using dotenv.net;
using System;
using System.Threading.Tasks;

// Load environment variables from .env file
DotEnv.Load();
var envVars = DotEnv.Read();

try
{
    string redisHost = envVars["REDIS_HOST"];
    string redisKey = envVars["REDIS_KEY"];

    if (string.IsNullOrEmpty(redisHost) || string.IsNullOrEmpty(redisKey))
    {
        Console.WriteLine("Error: REDIS_HOST and REDIS_KEY environment variables must be set in .env file.");
        Environment.Exit(1);
    }

    // Configure connection for Azure Managed Redis (Non-Clustered)
    var configurationOptions = new ConfigurationOptions
    {
        EndPoints = { { redisHost, 10000 } }, // Azure Managed Redis uses port 10000
        Password = redisKey,
        Ssl = true,
        ConnectTimeout = 30000, // 30 seconds
        SyncTimeout = 30000,
        AbortOnConnectFail = false,
        ConnectRetry = 3
    };

    Console.WriteLine($"Connecting to Redis (Non-Clustered) at {redisHost} on port 10000...");

    // Create connection
    using var redis = await ConnectionMultiplexer.ConnectAsync(configurationOptions);
    var database = redis.GetDatabase();

    // Test the connection
    var pingResult = await database.PingAsync();
    Console.WriteLine($"Ping returned: {pingResult.TotalMilliseconds} ms");
    Console.WriteLine("Connected to Redis successfully!");

    // Test basic operations with non-clustered Redis
    string testKey = "test_message";
    string testValue = "Hello from Non-Clustered Redis (.NET 10)!";
    
    await database.StringSetAsync(testKey, testValue);
    string? retrievedValue = await database.StringGetAsync(testKey);
    Console.WriteLine($"Set and retrieved test data: {retrievedValue}");

    Console.WriteLine("Redis connection will be disposed automatically.");
}
catch (RedisConnectionException ex)
{
    Console.WriteLine($"Connection error: {ex.Message}");
    Console.WriteLine("Check if Redis host and port are correct, and ensure network connectivity");
}
catch (RedisAuthenticationException ex)
{
    Console.WriteLine($"Authentication error: {ex.Message}");
    Console.WriteLine("Make sure the Redis key is correct and the service is accessible");
}
catch (RedisTimeoutError ex)
{
    Console.WriteLine($"Timeout error: {ex.Message}");
    Console.WriteLine("Check network latency and Redis server performance");
}
catch (Exception ex)
{
    Console.WriteLine($"Unexpected error: {ex.Message}");
    if (ex.Message.Contains("999"))
    {
        Console.WriteLine("Error 999 typically indicates a network connectivity issue or firewall restriction");
    }
}