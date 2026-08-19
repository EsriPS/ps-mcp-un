# Requirements Document

## Introduction

Add ArcGIS Enterprise OAuth support to PS-MCP so that MCP clients can authenticate using standard OAuth 2.1 flows. The server acts as an OAuth proxy — handling the client-facing OAuth ceremony while proxying authorization to the upstream ArcGIS Enterprise portal. The upstream ArcGIS token is stored encrypted and passed through to all tools via the existing `resolve_token()` mechanism, maintaining backward compatibility with the current token-passthrough mode.

## Glossary

- **OAuth_Proxy**: The FastMCP `OAuthProxy` component that acts as an intermediary OAuth server between MCP clients and the upstream ArcGIS Enterprise authorization server.
- **Upstream_Provider**: The ArcGIS Enterprise portal OAuth 2.0 endpoints (`/sharing/rest/oauth2/authorize` and `/sharing/rest/oauth2/token`).
- **MCP_Client**: Any Model Context Protocol client (Claude Desktop, Cursor, custom agents) connecting to PS-MCP via the streamable-http transport.
- **Token_Verifier**: The `ArcGISTokenVerifier` class that validates opaque ArcGIS tokens by calling the portal REST API.
- **Upstream_Token**: The opaque access token issued by ArcGIS Enterprise, used to authenticate requests to ArcGIS services.
- **Proxy_JWT**: The JWT token issued by the OAuth_Proxy to MCP_Clients, which encapsulates and secures the Upstream_Token.
- **Portal_URL**: The base URL of the ArcGIS Enterprise portal (e.g., `https://portal.example.com/portal`).
- **Client_Credentials**: The OAuth client_id and client_secret registered in ArcGIS Enterprise Portal as an "OAuth credentials" item.
- **Authorization_Code_Flow**: The OAuth 2.1 authorization code grant with PKCE, used to obtain tokens on behalf of a user.

## Requirements

### Requirement 1: OAuth Proxy Configuration

**User Story:** As a PS-MCP administrator, I want to configure the server to use OAuth proxy mode with ArcGIS Enterprise, so that MCP clients can authenticate via standard OAuth flows without needing pre-obtained tokens.

#### Acceptance Criteria

1. WHEN `USE_ARCGIS_OAUTH=True` is set in the environment, THE Server SHALL initialize the OAuth proxy using the `ARCGIS_PORTAL_URL`, `ARCGIS_OAUTH_CLIENT_ID`, and `ARCGIS_OAUTH_CLIENT_SECRET` environment variables, and the server SHALL complete startup only if all three values are present and non-empty.
2. WHEN `USE_ARCGIS_OAUTH=True` is set, THE Server SHALL read `ARCGIS_OAUTH_CLIENT_ID` and `ARCGIS_OAUTH_CLIENT_SECRET` from the environment to configure the upstream OAuth client credentials, treating a missing variable or an empty-string value as not configured.
3. IF `USE_ARCGIS_OAUTH=True` is set and `ARCGIS_PORTAL_URL` is not configured (missing or empty), THEN THE Server SHALL refuse to start and raise a startup error with a message indicating that `ARCGIS_PORTAL_URL` is required for OAuth proxy mode.
4. IF `USE_ARCGIS_OAUTH=True` is set and `ARCGIS_OAUTH_CLIENT_ID` is not configured (missing or empty), THEN THE Server SHALL refuse to start and raise a startup error with a message indicating that `ARCGIS_OAUTH_CLIENT_ID` is required for OAuth proxy mode.
5. IF `USE_ARCGIS_OAUTH=True` is set and `ARCGIS_OAUTH_CLIENT_SECRET` is not configured (missing or empty), THEN THE Server SHALL refuse to start and raise a startup error with a message indicating that `ARCGIS_OAUTH_CLIENT_SECRET` is required for OAuth proxy mode.
6. WHEN `USE_ARCGIS_OAUTH=True` is set, THE Server SHALL derive the upstream authorization endpoint as `{ARCGIS_PORTAL_URL}/sharing/rest/oauth2/authorize`, stripping any trailing slash from `ARCGIS_PORTAL_URL` before appending the path.
7. WHEN `USE_ARCGIS_OAUTH=True` is set, THE Server SHALL derive the upstream token endpoint as `{ARCGIS_PORTAL_URL}/sharing/rest/oauth2/token`, stripping any trailing slash from `ARCGIS_PORTAL_URL` before appending the path.
8. IF `USE_ARCGIS_OAUTH` is not set or is set to any value other than `True`, THEN THE Server SHALL skip OAuth proxy initialization and SHALL NOT require `ARCGIS_OAUTH_CLIENT_ID` or `ARCGIS_OAUTH_CLIENT_SECRET` to be present.

### Requirement 2: OAuth Proxy Server Behavior

**User Story:** As an MCP client developer, I want PS-MCP to expose standard OAuth 2.1 discovery and authorization endpoints, so that my client can authenticate without ArcGIS-specific knowledge.

#### Acceptance Criteria

1. THE OAuth_Proxy SHALL expose a `/.well-known/oauth-authorization-server` metadata endpoint that returns a JSON document containing at minimum: `issuer`, `authorization_endpoint`, `token_endpoint`, `response_types_supported`, `grant_types_supported`, `code_challenge_methods_supported`, and `token_endpoint_auth_methods_supported`.
2. THE OAuth_Proxy SHALL expose an authorization endpoint that accepts `response_type`, `client_id`, `redirect_uri`, `state`, `code_challenge`, and `code_challenge_method` parameters from the MCP_Client and redirects to the Upstream_Provider authorization page.
3. THE OAuth_Proxy SHALL expose a token endpoint that accepts an authorization code and returns a standard OAuth 2.1 token response containing `access_token`, `token_type`, and `expires_in` fields, where `access_token` is a Proxy_JWT.
4. WHEN an MCP_Client initiates the Authorization_Code_Flow, THE OAuth_Proxy SHALL substitute the MCP_Client's `client_id` with the configured upstream `ARCGIS_OAUTH_CLIENT_ID` and `ARCGIS_OAUTH_CLIENT_SECRET` when proxying the authorization request to the Upstream_Provider.
5. WHEN an MCP_Client initiates the Authorization_Code_Flow, THE OAuth_Proxy SHALL preserve the MCP_Client-provided `state` parameter through the upstream authorization and return it unmodified in the callback redirect to the MCP_Client.
6. WHEN the Upstream_Provider returns an authorization code via callback, THE OAuth_Proxy SHALL exchange the code for an Upstream_Token at the upstream token endpoint within a timeout of 30 seconds.
7. WHEN the OAuth_Proxy receives a valid Upstream_Token, THE OAuth_Proxy SHALL issue a Proxy_JWT to the MCP_Client that contains the Upstream_Token in encrypted form as a JWT claim.
8. THE OAuth_Proxy SHALL use `MCP_SERVER_BASE_URL` as its base URL for constructing callback URLs and metadata responses.

### Requirement 3: Token Passthrough to Tools

**User Story:** As a tool developer, I want the upstream ArcGIS token to be available via `resolve_token()` during tool execution, so that tools can authenticate with ArcGIS services transparently.

#### Acceptance Criteria

1. WHEN an MCP_Client makes a tool call with a valid Proxy_JWT, THE OAuth_Proxy SHALL decrypt the stored Upstream_Token and set it as the `access_token.token` value in the FastMCP per-request authentication context so that `get_access_token()` returns it.
2. WHEN `resolve_token()` is called during a tool execution authenticated via OAuth_Proxy, THE resolve_token function SHALL return the decrypted Upstream_Token.
3. THE resolve_token function SHALL maintain the existing resolution precedence: explicit parameter, then FastMCP auth context (including OAuth_Proxy tokens), then `ARCGIS_TOKEN` environment variable.
4. IF decryption of the Upstream_Token from the authentication context fails during a tool call, THEN THE OAuth_Proxy SHALL raise an AuthenticationError and not fall through to the `ARCGIS_TOKEN` environment variable.

### Requirement 4: Token Verification

**User Story:** As a security-conscious administrator, I want the server to validate upstream ArcGIS tokens before issuing proxy JWTs, so that only valid ArcGIS sessions produce authenticated MCP sessions.

#### Acceptance Criteria

1. WHEN the OAuth_Proxy receives an Upstream_Token from the token exchange, THE Token_Verifier SHALL validate the token by calling the ArcGIS portal REST API `/sharing/rest/portals/self` endpoint and the `/sharing/rest/community/self` endpoint, completing within 30 seconds per request.
2. IF the Upstream_Token fails validation against the portal REST API (non-200 status, error in response body, or request timeout), THEN THE OAuth_Proxy SHALL reject the token exchange and return an OAuth `invalid_grant` error response to the MCP_Client.
3. IF the ArcGIS portal is unreachable or the validation request times out, THEN THE OAuth_Proxy SHALL reject the token exchange and return an OAuth `server_error` error response to the MCP_Client.
4. THE Token_Verifier SHALL use the existing `ArcGISTokenVerifier` class to perform portal-based token validation.
5. WHILE `ARCGIS_VERIFY_SSL` is set to `"false"` (case-insensitive), THE Token_Verifier SHALL disable TLS certificate verification on validation requests to the portal; otherwise TLS verification SHALL be enabled by default.
6. IF `ARCGIS_PORTAL_URL` is not configured (neither via environment variable nor constructor parameter), THEN THE Token_Verifier SHALL raise a configuration error at initialization and refuse to start.

### Requirement 5: Backward Compatibility

**User Story:** As an existing PS-MCP user, I want the current token-passthrough authentication mode to continue working unchanged, so that my existing deployments are not disrupted.

#### Acceptance Criteria

1. IF `USE_ARCGIS_AUTH` is set to `"True"` and `USE_ARCGIS_OAUTH` is absent from the environment or set to any value other than `"True"`, THEN THE Server SHALL instantiate `ArcGISAuthProvider` (RemoteAuthProvider mode) and pass it as the `auth` parameter to the root `FastMCP` instance.
2. IF both `USE_ARCGIS_AUTH` and `USE_ARCGIS_OAUTH` are absent from the environment or set to any value other than `"True"`, THEN THE Server SHALL start without any authentication provider, allowing unauthenticated access to all MCP endpoints.
3. IF both `USE_ARCGIS_AUTH=True` and `USE_ARCGIS_OAUTH=True` are set, THEN THE Server SHALL use the OAuth_Proxy mode and emit a WARNING-level log message indicating that `USE_ARCGIS_AUTH` is being ignored in favor of OAuth proxy mode.
4. THE `resolve_token()` function SHALL maintain its existing signature (`token: str | None = None, required: bool = False`) and three-tier resolution order: explicit `token` argument first, FastMCP authentication context second, `ARCGIS_TOKEN` environment variable third, regardless of which authentication mode is active.
5. WHEN `ARCGIS_TOKEN` is set in the environment and no explicit token argument or FastMCP authentication context token is available, THE `resolve_token()` function SHALL return the value of `ARCGIS_TOKEN` regardless of which authentication mode is active or whether any authentication provider is configured.

### Requirement 6: OAuth Proxy Environment Configuration

**User Story:** As a PS-MCP administrator, I want all OAuth proxy settings to be configurable via environment variables, so that I can deploy the server in different environments without code changes.

#### Acceptance Criteria

1. THE Server SHALL read `USE_ARCGIS_OAUTH` from the environment and enable OAuth proxy mode when the value, compared case-insensitively, equals `"true"`; any other value or absence of the variable SHALL leave OAuth proxy mode disabled.
2. THE Server SHALL read `ARCGIS_OAUTH_CLIENT_ID` from the environment for the upstream OAuth client identifier, treating an empty string the same as an unset variable.
3. THE Server SHALL read `ARCGIS_OAUTH_CLIENT_SECRET` from the environment for the upstream OAuth client secret, treating an empty string the same as an unset variable.
4. THE Server SHALL read `MCP_SERVER_BASE_URL` from the environment for constructing OAuth callback and metadata URLs, defaulting to `http://localhost:8888` when not set, and stripping any trailing slash before use.
5. THE Server SHALL read `ARCGIS_PORTAL_URL` from the environment for deriving upstream OAuth endpoints, reusing the same variable used by the existing auth provider.
6. IF `USE_ARCGIS_OAUTH` is enabled and any of `ARCGIS_PORTAL_URL`, `ARCGIS_OAUTH_CLIENT_ID`, or `ARCGIS_OAUTH_CLIENT_SECRET` is missing or empty, THEN THE Server SHALL raise a startup error with a message identifying each missing variable by name.

### Requirement 7: Error Handling During OAuth Flow

**User Story:** As an MCP client developer, I want clear error responses when OAuth authentication fails, so that I can diagnose and resolve authentication issues.

#### Acceptance Criteria

1. IF the Upstream_Provider returns an error during the authorization callback (indicated by an `error` query parameter in the callback URL), THEN THE OAuth_Proxy SHALL return a standard OAuth error response with the `error` and `error_description` values from the Upstream_Provider.
2. IF the token exchange with the Upstream_Provider fails due to a network error (connection refused, DNS resolution failure, or request timeout exceeding 30 seconds), THEN THE OAuth_Proxy SHALL return an HTTP 502 response with an OAuth `server_error` error code and log the failure details including the exception type and message at ERROR level.
3. IF the token exchange with the Upstream_Provider fails due to invalid Client_Credentials (Upstream_Provider returns an error response with `error=invalid_client`), THEN THE OAuth_Proxy SHALL return an OAuth `invalid_client` error response with HTTP status 401.
4. IF an MCP_Client presents an expired Proxy_JWT (current time exceeds the `exp` claim) or a Proxy_JWT with an invalid signature, THEN THE OAuth_Proxy SHALL reject the request with an HTTP 401 response and a `WWW-Authenticate: Bearer error="invalid_token"` header.
5. THE OAuth_Proxy SHALL log all authentication failures at WARNING level including the failure stage (authorization, token_exchange, or token_verification), the error category, and the MCP_Client's client_id, without logging token values, authorization codes, or client secrets.
6. IF the OAuth `state` parameter returned in the callback does not match the `state` sent in the original authorization request, THEN THE OAuth_Proxy SHALL reject the callback with an OAuth `invalid_request` error response and log the mismatch at WARNING level.

### Requirement 8: PKCE Support

**User Story:** As a security-conscious MCP client developer, I want the OAuth flow to support PKCE, so that the authorization code exchange is protected against interception attacks.

#### Acceptance Criteria

1. WHEN an MCP_Client includes a `code_challenge` and `code_challenge_method` in the authorization request, THE OAuth_Proxy SHALL forward both parameters unmodified to the Upstream_Provider authorization endpoint.
2. WHEN an MCP_Client includes a `code_verifier` in the token exchange request, THE OAuth_Proxy SHALL forward the `code_verifier` parameter unmodified to the Upstream_Provider token endpoint.
3. THE OAuth_Proxy SHALL advertise PKCE support (`code_challenge_methods_supported: ["S256"]`) in the OAuth discovery metadata.
4. IF an MCP_Client sends an authorization request without a `code_challenge` parameter, THEN THE OAuth_Proxy SHALL reject the request with an OAuth `invalid_request` error response indicating that PKCE is required.
5. IF an MCP_Client sends an authorization request with a `code_challenge_method` value other than `S256`, THEN THE OAuth_Proxy SHALL reject the request with an OAuth `invalid_request` error response indicating the unsupported challenge method.
6. IF the Upstream_Provider returns a PKCE-related error during the token exchange, THEN THE OAuth_Proxy SHALL propagate the error to the MCP_Client as a standard OAuth error response.

### Requirement 9: Logging and Observability

**User Story:** As a PS-MCP administrator, I want OAuth authentication events to be logged, so that I can monitor authentication activity and troubleshoot issues.

#### Acceptance Criteria

1. WHEN the OAuth_Proxy is initialized at startup, THE Server SHALL log the configured Portal_URL and the authentication mode value (`USE_ARCGIS_OAUTH=True`) at INFO level.
2. WHEN an MCP_Client completes a successful OAuth flow, THE OAuth_Proxy SHALL log the authenticated username and the Portal_URL at INFO level.
3. WHEN an authentication attempt fails, THE OAuth_Proxy SHALL log the failure reason (including the stage of the OAuth flow that failed and the error category from the Upstream_Provider or Token_Verifier) at WARNING level without including token values, client secrets, or authorization codes.
4. THE OAuth_Proxy SHALL use the project standard logging pattern (`logger = logging.getLogger(__name__)` with lazy formatting).
5. WHILE the log level is set to DEBUG, THE OAuth_Proxy SHALL log OAuth flow stage transitions (authorization request initiated, callback received, token exchange initiated, token verification initiated) without including token values or secrets.
