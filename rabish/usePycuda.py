import gc



gc.collect()

import  pycuda
import pandas as pd

from pycuda import driver , compiler , gpuarray , tools
import numpy as np
import pycuda.autoinit



# this x ,  y is used for test function
# x = np.array(
#     [
#         [1,2,3,4,0],
#         [2,3,4,5,0]
#
#     ]
#
# ).astype(np.float32)
#
# y =  np.array(
#     [
#         [1,2,3,4,0],
#         [2,3,4,5,0],
#         [3,4,2,4,1],
#         [0,2,3,4,1]
#     ]
#
# ).astype(np.float32)

# z = np.empty((2,4))


# it is better to let col*attr < = 1e7
row_batch    = 6
batch_size   = 1
row          = row_batch*batch_size
col          = 31
attr         = 2
bandwith     = 4
block        = (row,1,1)
grid         = (col,batch_size,1)


matrixCal_template = u"""
    #include <math.h>


    __global__ void matrixMulKernel(float *x , float *y  , float *z ){
      
          int tx          =  threadIdx.x;
          int bix         =  blockIdx.x ; 
    const int NUMOFATTR   =  %(NUMOFATTR)s;
    const int COLOFOUT    =  gridDim.x ; //%(COLOFOUT)s;
    const int BATCHNUM    =  blockDim.y;
    const int ROWNUM      =  tx*BATCHNUM;
    //const int ROWOFOUT  =  blockDim.x ;   // %(ROWOFOUT)s;
          
    float s = 0;
    for (int idx  = 0 ; idx< NUMOFATTR ; idx++){
         s += pow(x[ROWNUM*NUMOFATTR+idx]-y[bix*NUMOFATTR+idx],2);
          //s += pow(x[1]-y[1],2) ; 
    }
    
    z[ROWNUM*COLOFOUT+bix] =sqrt(s); 
    
}



    __global__ void kernelCalculate(float *z){
          float bandwith      = %(bandwith)s ; 
          int   tx            =  threadIdx.x;
          int   bix           =  blockIdx.x ; 
    //const int   NUMOFATTR     =  %(NUMOFATTR)s;
    const int   COLOFOUT      =  gridDim.x ; //%(COLOFOUT)s;
    const int   BATCHNUM      =  blockDim.y;
    const int   ROWNUM        =  tx*BATCHNUM;
    //const int ROWOFOUT      =  blockDim.x ;   // %(ROWOFOUT)s;
    z[ROWNUM*COLOFOUT+bix]    =  z[ROWNUM*COLOFOUT+bix] / bandwith;    
    }
    
      __global__ void zsCal(float *z ,  float *s  , float *zs){
    
          
          int   tx            =  threadIdx.x;
          int   bix           =  blockIdx.x ; 
    //const int   NUMOFATTR   =  %(NUMOFATTR)s;
    const int   COLOFOUT      =  gridDim.x ; //%(COLOFOUT)s;
    const int   BATCHNUM      =  blockDim.y;
    const int   ROWNUM        =  tx*BATCHNUM;
    //const int ROWOFOUT      =  blockDim.x ;   // %(ROWOFOUT)s;
    zs[ROWNUM*COLOFOUT+bix]   = s[ROWNUM*COLOFOUT+bix] * z[ROWNUM*COLOFOUT+bix] ; 
    
    
    }
  
"""




matrixCal = matrixCal_template%{

    'NUMOFATTR':attr,
    'COLOFOUT':col,
    'ROWOFOUT':row,
    'bandwith' : bandwith
}



# get function


mod               = compiler.SourceModule(matrixCal)
matrixMul         = mod.get_function("matrixMulKernel")
kernelCalculate   = mod.get_function("kernelCalculate")
zsCal             = mod.get_function("zsCal")




# model paras

# this x , y is used for test grid used


# prepare data here
#test for power and limit

# you must change the type to float32
# x            = np.random.random((row,attr)).astype(np.float32)
# y            = np.random.random((col,attr)).astype(np.float32)
# r            = np.random.random((col,1)).astype(np.float32)
# s            = np.random.random((row,col)).astype(np.float32)
#


# test for algorithmn
x             = np.arange(row*attr).reshape((row,attr)).astype(np.float32)
y             = np.arange(10,col*attr+10).reshape((col,attr)).astype(np.float32)
z             = np.empty((row,col))
s             = np.arange(5,row*col+5).reshape((row,col)).astype(np.float32)
r             = np.arange(col).reshape((col,1)).astype(np.float32)

#def main(x,y,r,s,row,col,block,grid):

x_gpu        = gpuarray.to_gpu(x)
y_gpu        = gpuarray.to_gpu(y)
s_gpu        = gpuarray.to_gpu(s)
z_gpu        = gpuarray.empty((row,col),np.float32)
zs_gpu       = gpuarray.empty((row,col),np.float32)




matrixMul(x_gpu,y_gpu,z_gpu,block = block,grid = grid )

kernelCalculate(z_gpu, block = block,grid = grid )


zsCal(z_gpu,s_gpu,zs_gpu, block = block,grid = grid)

zs = zs_gpu.get()

wr = zs.dot(r)
sum_zs = zs.dot(np.ones((col,1)).astype(np.float32))

























