# ArcGIS Enterprise Authentication Guide

## Overview

This service provides tools for interacting with ArcGIS Enterprise, including user authentication, content discovery, and item management.

## Authentication

ArcGIS Enterprise uses token-based authentication. You need to provide a valid authentication token when calling the tools in this service.

### Getting a Token

To obtain an authentication token, you can:

1. **Portal Token Generator**: Navigate to `https://<your-portal>/sharing/rest/generateToken`
2. **OAuth 2.0**: Use the OAuth 2.0 authentication flow with your client ID and secret
3. **Username/Password**: Generate a token programmatically using your ArcGIS Enterprise credentials

### Token Validation

All tools in this service validate the provided token before performing operations. If a token is invalid or expired, you'll receive an authentication error.

## Available Tools

### get_user_info

Validates an authentication token and retrieves detailed user information.

**Parameters:**
- `token` (required): Valid ArcGIS Enterprise authentication token

**Returns:**
- User profile information including username, full name, email, role, organization ID, and privileges

**Example Use Case:**
- Verify token validity before performing operations
- Check user permissions and access levels
- Display current user information in an application

### list_user_content

Lists content items owned by a specific user or the authenticated user.

**Parameters:**
- `token` (required): Valid ArcGIS Enterprise authentication token
- `username` (optional): Username to list content for (defaults to authenticated user)
- `folder` (optional): Specific folder to list content from
- `num` (optional): Maximum number of items to return (default: 10, max: 100)
- `start` (optional): Starting index for pagination (default: 1)

**Returns:**
- List of content items with metadata
- Total count of items
- Pagination information

**Example Use Cases:**
- Browse user's web maps, layers, and applications
- Discover available content for analysis
- Audit user-owned content

### get_item_info

Retrieves detailed information about a specific content item.

**Parameters:**
- `token` (required): Valid ArcGIS Enterprise authentication token
- `item_id` (required): Unique identifier of the item

**Returns:**
- Comprehensive item metadata including type, description, tags, sharing settings, URLs, and timestamps

**Example Use Cases:**
- Get details about a web map or feature service
- Check item sharing settings and permissions
- Retrieve item metadata for documentation

## Environment Variables

The following environment variables must be configured:

- **ARCGIS_PORTAL_URL**: URL of the ArcGIS Enterprise portal (e.g., `https://portal.example.com/arcgis`)
- **ARCGIS_CLIENT_ID**: OAuth client ID for application authentication
- **ARCGIS_CLIENT_SECRET**: OAuth client secret for application authentication
- **ARCGIS_VERIFY_SSL**: Whether to verify SSL certificates (default: `True`)

## Error Handling

The service uses custom exceptions for clear error reporting:

- **AuthenticationError** (401): Token is invalid, expired, or authentication failed
- **ServiceUnavailableError** (503): Cannot connect to ArcGIS Enterprise
- **General Errors** (500): Unexpected errors during operation

## Best Practices

1. **Token Management**: Always validate tokens before performing multiple operations
2. **Error Handling**: Check for authentication errors and handle them gracefully
3. **Permissions**: Respect user permissions and access levels when accessing content
4. **Pagination**: Use pagination parameters when listing large amounts of content
5. **SSL Verification**: Enable SSL verification in production environments

## Additional Resources

- [ArcGIS REST API Documentation](https://developers.arcgis.com/rest/)
- [ArcGIS Enterprise Authentication](https://developers.arcgis.com/documentation/mapping-apis-and-services/security/)
- [OAuth 2.0 in ArcGIS](https://developers.arcgis.com/documentation/mapping-apis-and-services/security/oauth-2.0/)

