import { useState } from "react";
import { ApiError, api, type Session } from "../api";

export function SignIn({
  onSignedIn,
}: {
  onSignedIn: (session: Session) => void;
}) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = username.trim().length >= 3 && password.length >= 8;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const session =
        mode === "login"
          ? await api.logIn(username.trim(), password)
          : await api.signUp(username.trim(), password, username.trim());
      onSignedIn(session);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel sign-in">
      <form
        className="sign-in-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready && !busy) submit();
        }}
      >
        <label>
          Username
          <input
            value={username}
            autoComplete="username"
            placeholder="username"
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            autoComplete={
              mode === "login" ? "current-password" : "new-password"
            }
            placeholder={mode === "signup" ? "at least 8 characters" : ""}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="primary" type="submit" disabled={!ready || busy}>
          {busy ? "Working…" : mode === "login" ? "Log in" : "Sign up"}
        </button>
      </form>

      <button
        className="link"
        onClick={() => {
          setMode(mode === "login" ? "signup" : "login");
          setError(null);
        }}
      >
        {mode === "login"
          ? "New here? Create an account"
          : "Already have an account? Log in"}
      </button>

      {error && <p className="error">{error}</p>}
    </section>
  );
}
