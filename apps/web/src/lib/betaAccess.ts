export interface BetaAccessCredentials {
  username: string;
  password: string;
}

function constantTimeEqual(actual: string, expected: string): boolean {
  const maxLength = Math.max(actual.length, expected.length);
  let mismatch = actual.length ^ expected.length;

  for (let index = 0; index < maxLength; index += 1) {
    mismatch |= (actual.charCodeAt(index) || 0) ^ (expected.charCodeAt(index) || 0);
  }
  return mismatch === 0;
}

function decodeBasicCredentials(authorization: string): BetaAccessCredentials | null {
  const [scheme, encoded, ...rest] = authorization.trim().split(/\s+/);
  if (scheme?.toLowerCase() !== "basic" || !encoded || rest.length > 0) return null;

  try {
    const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
    const decoded = new TextDecoder().decode(bytes);
    const separator = decoded.indexOf(":");
    if (separator < 0) return null;
    return {
      username: decoded.slice(0, separator),
      password: decoded.slice(separator + 1),
    };
  } catch {
    return null;
  }
}

/** Webの共有認証を検証する。資格情報自体はログや画面へ返さない。 */
export function hasValidBetaAccess(
  authorization: string | null,
  expected: BetaAccessCredentials,
): boolean {
  if (!authorization) return false;
  const actual = decodeBasicCredentials(authorization);
  if (!actual) return false;
  const usernameMatches = constantTimeEqual(actual.username, expected.username);
  const passwordMatches = constantTimeEqual(actual.password, expected.password);
  return usernameMatches && passwordMatches;
}
