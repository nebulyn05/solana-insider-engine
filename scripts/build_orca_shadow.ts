import { swapInstructions, WhirlpoolDeployment } from "@orca-so/whirlpools";
import {
  address, appendTransactionMessageInstructions, compileTransaction,
  createNoopSigner, createSolanaRpc, getBase64EncodedWireTransaction,
  createTransactionMessage, setTransactionMessageFeePayer,
  setTransactionMessageLifetimeUsingBlockhash,
} from "@solana/kit";

type Args={pool:string;inputMint:string;amount:bigint;user:string;slippageBps:number;rpcUrl:string};

function parseArgs(argv:string[]):Args{
  const values=new Map<string,string>();
  for(let i=0;i<argv.length;i+=2){
    const key=argv[i],value=argv[i+1];
    if(!key?.startsWith("--")||value===undefined) throw new Error("Invalid arguments");
    values.set(key.slice(2),value);
  }
  const pool=values.get("pool"),inputMint=values.get("input-mint"),amountText=values.get("amount"),user=values.get("user");
  if(!pool||!inputMint||!amountText||!user) throw new Error("pool, input-mint, amount, and user are required");
  const slippageBps=Number(values.get("slippage-bps")??"100");
  if(!Number.isInteger(slippageBps)||slippageBps<0||slippageBps>10000) throw new Error("invalid slippage-bps");
  return {pool,inputMint,amount:BigInt(amountText),user,slippageBps,rpcUrl:values.get("rpc-url")??"https://api.mainnet.solana.com"};
}

async function main(){
  const args=parseArgs(process.argv.slice(2));
  const rpc=createSolanaRpc(args.rpcUrl);
  const user=address(args.user);
  const {instructions,quote}=await swapInstructions(
    rpc,{inputAmount:args.amount,mint:address(args.inputMint)},address(args.pool),
    {slippageToleranceBps:args.slippageBps,signer:createNoopSigner(user),whirlpoolDeployment:WhirlpoolDeployment.mainnet}
  );
  const {value:{blockhash,lastValidBlockHeight}}=await rpc.getLatestBlockhash().send();
  let message=createTransactionMessage({version:0});
  message=setTransactionMessageFeePayer(user,message);
  message=setTransactionMessageLifetimeUsingBlockhash({blockhash,lastValidBlockHeight},message);
  message=appendTransactionMessageInstructions(instructions,message);
  const transaction=compileTransaction(message);
  console.log(JSON.stringify({
    protocol:"orca_whirlpool",cluster:"mainnet-beta",pool:args.pool,input_mint:args.inputMint,user:args.user,
    amount_base_units:args.amount.toString(),slippage_bps:args.slippageBps,instruction_count:instructions.length,
    quote:serializeBigInts(quote),transaction_base64:getBase64EncodedWireTransaction(transaction),signed:false,broadcast:false
  },null,2));
}
function serializeBigInts(value:unknown):unknown{
  if(typeof value==="bigint") return value.toString();
  if(Array.isArray(value)) return value.map(serializeBigInts);
  if(value&&typeof value==="object") return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,serializeBigInts(v)]));
  return value;
}
main().catch(error=>{console.error(error instanceof Error?error.message:String(error));process.exitCode=1});
