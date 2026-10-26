import { QueuePage } from "./QueuePage";

export function App() {
  return (
    <>
      <header className="header">
        <a className="brand" href="#/">
          UnderCover
        </a>
        <nav aria-label="Main">
          <a href="#/">Queue</a>
          <a href="#/instructions">Instructions</a>
        </nav>
      </header>
      <main className="page">
        <QueuePage />
      </main>
    </>
  );
}
