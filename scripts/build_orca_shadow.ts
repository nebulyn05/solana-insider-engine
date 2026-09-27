import {
  swapInstructions,
  WhirlpoolDeployment,
} from "@orca-so/whirlpools";
import {
  address,
  appendTransactionMessageInstructions,
  compileTransaction,
  createNoopSigner,
  createSolanaRpc,
  createTransactionMessage,
  getBase64EncodedWireTransaction,
  setTransactionMessageFeePayer,
  setTransactionMessageLifetimeUsingBlockhash,
} from "@solana/kit";

type Args = {
  pool: string;
  inputMint: string;
  amount: bigint;
  user: string;
  slippageBps: number;
  rpcUrl: string;
};

function parseArgs(argv: string[]): Args {
  const values = new Map<string, string>();
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    const value = argv[i + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(
        "Usage: npm run build:orca-shadow -- --pool <pool> --input-mint <mint> --amount <base-units> --user <address> [--slippage-bps <bps>] [--rpc-url <url>]",
      );
    }
    values.set(key.slice(2), value);
  }

  const pool = values.get("pool");
  const inputMint = values.get("input-mint");
  const amountText = values.get("amount");
  const user = values.get("user");

  if (!pool || !inputMint || !amountText || !user) {
    throw new Error(
      "pool, input-mint, amount, and user are required",
    );
  }

  const slippageBps = Number(values.get("slippage-bps") ?? "100");
  if (!Number.isInteger(slippageBps) || slippageBps < 0 || slippageBps > 10_000) {
    throw new Error("slippage-bps must be an integer from 0 to 10000");
  }

  return {
    pool,
    inputMint,
    amount: BigInt(amountText),
    user,
    slippageBps,
    rpcUrl: values.get("rpc-url") ?? "https://api.devnet.solana.com",
  };
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const rpc = createSolanaRpc(args.rpcUrl);
  const user = address(args.user);

  /*
   * Orca's Devnet deployment is used explicitly. The signer is a no-op signer:
   * it contributes the user's public address to instruction account metadata,
   * but it cannot sign or submit a transaction.
   */
  const { instructions, quote } = await swapInstructions(
    rpc,
    {
      inputAmount: args.amount,
      mint: address(args.inputMint),
    },
    address(args.pool),
    {
      slippageToleranceBps: args.slippageBps,
      signer: createNoopSigner(user),
      whirlpoolDeployment: WhirlpoolDeployment.devnet,
    },
  );

  const {
    value: { blockhash, lastValidBlockHeight },
  } = await rpc.getLatestBlockhash().send();

  let message = createTransactionMessage({ version: 0 });
  message = setTransactionMessageFeePayer(user, message);
  message = setTransactionMessageLifetimeUsingBlockhash(
    { blockhash, lastValidBlockHeight },
    message,
  );
  message = appendTransactionMessageInstructions(instructions, message);

  const transaction = compileTransaction(message);
  const encoded = getBase64EncodedWireTransaction(transaction);

  console.log(
    JSON.stringify(
      {
        protocol: "orca_whirlpool",
        cluster: "devnet",
        pool: args.pool,
        input_mint: args.inputMint,
        user: args.user,
        amount_base_units: args.amount.toString(),
        slippage_bps: args.slippageBps,
        instruction_count: instructions.length,
        quote: serializeBigInts(quote),
        transaction_base64: encoded,
        signed: false,
        broadcast: false,
      },
      null,
      2,
    ),
  );
}

function serializeBigInts(value: unknown): unknown {
  if (typeof value === "bigint") {
    return value.toString();
  }
  if (Array.isArray(value)) {
    return value.map(serializeBigInts);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        serializeBigInts(item),
      ]),
    );
  }
  return value;
}

main().catch((error: unknown) => {
  console.error(
    error instanceof Error ? error.message : String(error),
  );
  process.exitCode = 1;
});
