# Setting Up GitHub Webhook for Atlantis

This guide will walk you through setting up a GitHub webhook to connect your repository with Atlantis for automated Terraform operations.

## Prerequisites

1. You have filled out the `.env` file with your GitHub credentials:
   - `GITHUB_USER`: Your GitHub username
   - `GITHUB_TOKEN`: Your GitHub personal access token with repo scope
   - `GH_WEBHOOK_SECRET`: A secure random string for webhook authentication

2. Your Atlantis server is accessible from the internet or you're using a tool like ngrok for testing

## Creating the GitHub Webhook

1. **Navigate to your GitHub repository**

2. **Go to Repository Settings**
   - Click on "Settings" in the top navigation bar of your repository

3. **Select Webhooks**
   - In the left sidebar, click on "Webhooks"
   - Click the "Add webhook" button

4. **Configure the webhook**
   - **Payload URL**: Enter your Atlantis server URL with the `/events` endpoint
     - Format: `http://your-server-address:4141/events`
     - For local testing with ngrok: `https://your-ngrok-url.ngrok.io/events`
   
   - **Content type**: Select `application/json`
   
   - **Secret**: Enter the same value you used for `GH_WEBHOOK_SECRET` in your `.env` file
   
   - **Which events would you like to trigger this webhook?**:
     - Select "Let me select individual events"
     - Check: "Pull requests" and "Pushes"
     
   - **Active**: Ensure this is checked
   
   - Click "Add webhook" to save

5. **Verify webhook setup**
   - GitHub will send a ping event to your webhook
   - You should see a green checkmark if the connection was successful
   - You can view the delivery details by clicking on the webhook in the list

## Testing the Webhook

1. **Create a new pull request** in your repository with Terraform changes

2. **Observe Atlantis logs**
   - Run `docker-compose logs -f atlantis` to see incoming webhook events
   - You should see Atlantis responding to the pull request with a plan

3. **Check GitHub pull request**
   - Atlantis should comment on your pull request with the Terraform plan output
   - You can approve and apply the plan directly from the GitHub interface

## Troubleshooting

### Webhook Not Triggering

- Check that your webhook URL is accessible from the internet
- Verify the webhook secret matches between GitHub and your `.env` file
- Ensure your GitHub token has the necessary permissions

### Authentication Errors

- Verify your GitHub token is valid and has not expired
- Check that your GitHub username is correct
- Ensure your repository is included in the `ATLANTIS_REPO_ALLOWLIST`

### Plan/Apply Failures

- Check Atlantis logs for specific error messages
- Verify that your Terraform configuration is valid
- Ensure all required variables are provided

## Additional Resources

- [Atlantis Webhook Documentation](https://www.runatlantis.io/docs/configuring-webhooks.html)
- [GitHub Webhooks Documentation](https://docs.github.com/en/developers/webhooks-and-events/webhooks/about-webhooks)
