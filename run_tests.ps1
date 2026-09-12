
cd local-agent
echo "Running A..."
.\voila.exe --test-dag-a > taskA.log 2>&1
echo "Running B..."
.\voila.exe --test-dag-b > taskB.log 2>&1
echo "Running C..."
.\voila.exe --test-dag-c > taskC.log 2>&1
echo "Running D..."
.\voila.exe --test-dag-d > taskD.log 2>&1
echo "Running E..."
.\voila.exe --test-dag-e > taskE.log 2>&1
echo "All done!"

