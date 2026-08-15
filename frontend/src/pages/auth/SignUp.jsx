import { SignUp as ClerkSignUp } from '@clerk/clerk-react';

export const SignUp = () => {
  return <ClerkSignUp routing="path" path="/signup" signInUrl="/login" />;
};
