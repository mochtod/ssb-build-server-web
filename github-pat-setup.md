# Creating a GitHub Personal Access Token for Atlantis

This guide will walk you through creating a GitHub Personal Access Token (PAT) with the necessary permissions for Atlantis to interact with your GitHub repositories.

## Prerequisites

- A GitHub account
- Access to at least one repository where you want to use Atlantis

## Steps to Create a Personal Access Token

1. **Log in to GitHub**
   - Navigate to [github.com](https://github.com) and sign in

2. **Access Developer Settings**
   - Click on your profile picture in the top-right corner
   - Select "Settings" from the dropdown menu
   - Scroll down to the bottom of the left sidebar and click on "Developer settings"

3. **Generate a Personal Access Token**
   - In the left sidebar, click on "Personal access tokens"
   - Click on "Tokens (classic)" (or go directly to [https://github.com/settings/tokens](https://github.com/settings/tokens))
   - Click "Generate new token" → "Generate new token (classic)"

4. **Configure Token Settings**
   - **Note**: Enter a descriptive name like "Atlantis Terraform Operations"
   - **Expiration**: Choose an appropriate expiration date (consider security requirements)
   - **Scopes**: Select the following permissions:
     - `repo` (all repo permissions) - Required for Atlantis to access repositories, create pull request comments, etc.
     - If you're using GitHub organizations, also select:
       - `read:org` - Required for Atlantis to check organization membership

5. **Generate Token**
   - Scroll to the bottom and click "Generate token"

6. **Copy and Store Token Securely**
   - The token will be displayed only once
   - Copy the token immediately
   - Store it securely (e.g., in a password manager)
   - Add it to your `.env` file as the `GITHUB_TOKEN` value

## Security Considerations

- **Token Privileges**: The token provides access to repositories, so keep it secure
- **Token Rotation**: Plan to rotate the token periodically for better security
- **Expiration**: Setting an expiration date ensures the token won't be valid indefinitely
- **Scope Limitation**: Only select the permissions that Atlantis needs

## Using the Token

1. Update your `.env` file with:
   ```
   GITHUB_USER=your-github-username
   GITHUB_TOKEN=your-personal-access-token
   ```

2. When you restart Atlantis with `docker-compose down && docker-compose up -d`, it will use these credentials to authenticate with GitHub.

## Troubleshooting

### Common Issues

- **401 Unauthorized errors**: Verify your token is correct and hasn't expired
- **403 Forbidden errors**: Check that your token has the necessary scopes
- **Token not working for organization repositories**: Ensure you've added the `read:org` scope

### Verifying Token Permissions

You can test if your token is configured correctly by running:

```bash
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
```

Replace `YOUR_TOKEN` with your actual token. If successful, you'll see your GitHub user information in the response.

### Token Revocation

If you need to revoke a token (e.g., if it's been compromised):
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Find the token in the list and click "Delete"
3. Generate a new token and update your `.env` file

## Next Steps

After setting up your Personal Access Token:
1. Complete the webhook setup as outlined in `github-webhook-setup.md`
2. Restart your Docker containers to apply the new configuration
3. Test the integration by creating a pull request with Terraform changes
