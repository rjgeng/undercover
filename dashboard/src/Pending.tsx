export function Pending({ error }: Readonly<{ error: string | undefined }>) {
  return error ? (
    <p className="alert" role="alert">
      {error}
    </p>
  ) : (
    <p className="muted" role="status">
      Loading
    </p>
  );
}
