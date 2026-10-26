import { useEffect, useState } from "react";

export type Route =
  | { page: "queue" }
  | { page: "claim"; claimId: string }
  | { page: "instructions" };

export function parseRoute(hash: string): Route {
  const [page = "", claimId = ""] = hash.replace(/^#\/?/, "").split("/");
  if (page === "claims" && claimId) return { page: "claim", claimId };
  if (page === "instructions") return { page: "instructions" };
  return { page: "queue" };
}

export function useRoute(): Route {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => {
      setHash(window.location.hash);
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);
  return parseRoute(hash);
}
