import { ClaimPage } from "./ClaimPage";
import { InstructionsPage } from "./InstructionsPage";
import { QueuePage } from "./QueuePage";
import { useRoute, type Route } from "./route";

export function App() {
  const route = useRoute();
  return (
    <>
      <header className="header">
        <a className="brand" href="#/">
          UnderCover
        </a>
        <nav aria-label="Main">
          <a href="#/" aria-current={current(route, "queue")}>
            Queue
          </a>
          <a
            href="#/instructions"
            aria-current={current(route, "instructions")}
          >
            Instructions
          </a>
        </nav>
      </header>
      <main className="page">
        <Page route={route} />
      </main>
    </>
  );
}

function current(route: Route, page: Route["page"]) {
  return route.page === page ? "page" : undefined;
}

function Page({ route }: Readonly<{ route: Route }>) {
  switch (route.page) {
    case "claim":
      return <ClaimPage key={route.claimId} claimId={route.claimId} />;
    case "instructions":
      return <InstructionsPage />;
    case "queue":
      return <QueuePage />;
  }
}
