import { SignUp } from "@clerk/nextjs";

export default function Page() {
  return (
    <main className="shell auth-shell">
      <SignUp path="/sign-up" routing="path" signInUrl="/sign-in" />
    </main>
  );
}
