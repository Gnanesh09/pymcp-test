import { SignIn } from "@clerk/nextjs";

export default function Page() {
  return (
    <main className="shell auth-shell">
      <SignIn path="/sign-in" routing="path" signUpUrl="/sign-up" />
    </main>
  );
}
